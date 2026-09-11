"""Disposable PostgreSQL integration: transactions, idempotency, isolation and races."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from unittest.mock import Mock

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.routes.portfolio import get_portfolio_service
from app.auth.dependencies import get_current_user
from app.main import app
from app.market.providers import ProviderError
from app.market.schemas import MarketAsset
from app.portfolio.repository import PostgresPortfolioRepository
from app.portfolio.risk import PortfolioError
from app.portfolio.schemas import PortfolioCreate, RiskSettings
from app.portfolio.service import PortfolioService
from .test_accounting import request

DSN = os.getenv('PREDICTION_TEST_DSN')
pytestmark = pytest.mark.skipif(not DSN, reason='Disposable PostgreSQL service is not configured')


@pytest.fixture
def setup():
    with psycopg.connect(DSN) as c:
        root = Path(__file__).resolve().parents[3] / 'database' / 'postgres'
        for file in ['001_initial.sql', '002_auth.sql', '004_portfolio.sql', '004_portfolio.sql']:
            c.execute((root / file).read_text())
        user = c.execute("INSERT INTO users (username,email,password_hash) VALUES ('portfolio-test',%s,'unused') RETURNING user_id", (f'{uuid4()}@example.test',)).fetchone()[0]
    market = Mock()
    market.get_top_assets.return_value = ([MarketAsset(id='bitcoin', symbol='BTC', name='Bitcoin', current_price=120, last_updated=datetime.now(timezone.utc))], False)
    service = PortfolioService(PostgresPortfolioRepository(DSN), market)
    portfolio = service.create(user, PortfolioCreate(initial_cash=1000))['portfolio_id']
    yield service, user, portfolio
    with psycopg.connect(DSN) as c:
        # Delete fills before orders because the immutable fill FK is restrictive.
        c.execute('DELETE FROM portfolio_trades WHERE portfolio_id=%s', (portfolio,))
        c.execute('DELETE FROM users WHERE user_id=%s', (user,))


def test_reserve_fill_partial_sale_cancellation_and_idempotency(setup):
    s, u, p = setup
    assert s.create(u, PortfolioCreate(initial_cash=9999))['portfolio_id'] == p
    assert s.preview(u, p, request())['cash_required'] == 202
    assert not s.overview(u, p)['pending_orders']
    req = request()
    order = s.reserve(u, p, req)
    assert s.reserve(u, p, req)['order_id'] == order['order_id']
    with pytest.raises(PortfolioError, match='different'):
        s.reserve(u, p, req.model_copy(update={'symbol': 'ETH'}))
    assert s.overview(u, p)['available_cash'] == 798
    s.complete(u, p, order['order_id'], 'fill')
    s.complete(u, p, order['order_id'], 'fill')
    assert len(s.history(u, p, 25, None)['items']) == 1
    snapshot = s.overview(u, p)
    assert snapshot['total_pnl'] == 38 and snapshot['holdings'][0]['cost_basis'] == 202
    sell = s.reserve(u, p, request(side='sell', quantity='1', simulation_price='120', fee='1'))
    assert s.overview(u, p)['holdings'][0]['available_quantity'] == 1
    s.complete(u, p, sell['order_id'], 'fill')
    snapshot = s.overview(u, p)
    assert snapshot['cash_balance'] == 917 and snapshot['realized_pnl'] == 18
    assert snapshot['total_value'] - snapshot['initial_cash'] == snapshot['total_pnl'] == 37
    page = s.history(u, p, 1, None)
    assert page['next_cursor'] and len(s.history(u, p, 1, page['next_cursor'])['items']) == 1
    pending = s.reserve(u, p, request(symbol='ETH'))
    s.complete(u, p, pending['order_id'], 'cancel')
    s.complete(u, p, pending['order_id'], 'cancel')
    assert s.overview(u, p)['reserved_cash'] == 0
    with pytest.raises(PortfolioError, match='cancelled'):
        s.complete(u, p, pending['order_id'], 'fill')


def test_ownership_all_paths_and_http_decimal_responses(setup):
    s, u, p = setup
    order = s.reserve(u, p, request())
    for operation in [lambda: s.overview(u + 999999, p), lambda: s.preview(u + 999999, p, request()),
                      lambda: s.reserve(u + 999999, p, request()), lambda: s.settings(u + 999999, p, RiskSettings()),
                      lambda: s.complete(u + 999999, p, order['order_id'], 'fill'), lambda: s.history(u + 999999, p, 25, None)]:
        with pytest.raises(PortfolioError) as error:
            operation()
        assert error.value.status_code == 404
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_current_user] = lambda: {'user_id': u}
    app.dependency_overrides[get_portfolio_service] = lambda: s
    try:
        client = TestClient(app)
        assert client.get('/api/v1/portfolios').json()[0]['portfolio_id'] == p
        assert client.get(f'/api/v1/portfolios/{p}').json()['available_cash'] == '798.00000000'
        assert client.post(f'/api/v1/portfolios/{p}/orders/{order["order_id"]}/fill').status_code == 200
        assert client.post(f'/api/v1/portfolios/{p}/orders', json=request().model_dump(mode='json')).status_code == 200
        assert client.put(f'/api/v1/portfolios/{p}/risk', json=RiskSettings().model_dump(mode='json')).status_code == 200
        assert client.get(f'/api/v1/portfolios/{p}/trades?limit=0').status_code == 422
        app.dependency_overrides[get_current_user] = lambda: {'user_id': u + 999999}
        assert client.get(f'/api/v1/portfolios/{p}').status_code == 404
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_concurrent_reservations_cannot_overspend(setup):
    s, u, p = setup
    def submit(_):
        try:
            return s.reserve(u, p, request(quantity='6', fee='0'))['status']
        except PortfolioError as error:
            return str(error)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert sorted(results) == ['Insufficient available cash', 'pending']
    assert s.overview(u, p)['available_cash'] == 400


def test_concurrent_fills_and_sells_are_exactly_once(setup):
    s, u, p = setup
    order = s.reserve(u, p, request())
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: s.complete(u, p, order['order_id'], 'fill'), range(2)))
    assert len(s.history(u, p, 25, None)['items']) == 1
    def sell(_):
        try:
            return s.reserve(u, p, request(side='sell', quantity='2'))['status']
        except PortfolioError as error:
            return str(error)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(sell, range(2))) == ['Insufficient available holding', 'pending']


def test_settings_cannot_break_existing_reservations_and_quotes_expire(setup):
    s, u, p = setup
    first = s.reserve(u, p, request())
    s.reserve(u, p, request(symbol='ETH'))
    with pytest.raises(PortfolioError, match='lowering'):
        s.settings(u, p, RiskSettings(max_open_positions=1))
    with pytest.raises(PortfolioError, match='lowering'):
        s.settings(u, p, RiskSettings(max_open_trades=1))
    s.complete(u, p, first['order_id'], 'fill')
    s.market.get_top_assets.return_value[0][0].last_updated = datetime.now(timezone.utc) - timedelta(minutes=6)
    assert s.overview(u, p)['total_value'] is None
    s.market.get_top_assets.side_effect = ProviderError('offline')
    assert s.overview(u, p)['available_cash'] == 596
