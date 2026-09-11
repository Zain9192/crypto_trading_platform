from datetime import datetime, timezone
from decimal import Decimal as D
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.portfolio.accounting import apply_fill, reservations
from app.portfolio.risk import PortfolioError, validate_order
from app.portfolio.schemas import PaperOrderCreate, RiskSettings
from app.portfolio.service import value_snapshot


def request(**kw):
    return PaperOrderCreate(client_order_id=uuid4(), **{"symbol": "BTC", "side": "buy", "quantity": "2", "simulation_price": "100", "fee": "2", **kw})


def test_fees_partial_sales_and_final_basis_reconcile():
    holding = {"quantity": D(0), "cost_basis": D(0), "realized_pnl": D(0)}
    holding, cash, pnl = apply_fill(holding, 'buy', D(3), D(100), D(1))
    assert cash == -301 and pnl == 0
    holding, proceeds, pnl = apply_fill(holding, 'sell', D(1), D(120), D(1))
    assert pnl == D('18.66666667')
    holding, last_proceeds, last_pnl = apply_fill(holding, 'sell', D(2), D(90), D(1))
    assert holding['quantity'] == holding['cost_basis'] == 0
    assert holding['realized_pnl'] == cash + proceeds + last_proceeds == -3
    assert pnl + last_pnl == -3


def test_weighted_cost_multiple_buys():
    holding = {"quantity": D(1), "cost_basis": D(101), "realized_pnl": D(8)}
    updated, cash, _ = apply_fill(holding, 'buy', D(2), D(200), D(2))
    assert updated == {"quantity": D(3), "cost_basis": D(503), "realized_pnl": D(8)}
    assert cash == -402


@pytest.mark.parametrize('fields', [dict(quantity='NaN'), dict(simulation_price='Infinity'), dict(fee='-1'),
    dict(quantity='0'), dict(quantity='0.000000001'), dict(symbol='../BTC'), dict(side='short')])
def test_invalid_numeric_and_symbol_inputs(fields):
    with pytest.raises(ValidationError):
        request(**fields)


def test_risk_cash_fees_positions_and_reserved_units():
    pending = [{"symbol": "ETH", "side": "buy", "notional": D(800), "fee": D(2), "quantity": D(1)}]
    with pytest.raises(PortfolioError, match='cash'):
        validate_order({"cash_balance": D(1000)}, [], pending, request(), RiskSettings())
    with pytest.raises(PortfolioError, match='positions'):
        validate_order({"cash_balance": D(2000)}, [], pending, request(), RiskSettings(max_open_positions=1))
    with pytest.raises(PortfolioError, match='trades'):
        validate_order({"cash_balance": D(2000)}, [], pending, request(), RiskSettings(max_open_trades=1))
    pending = [{"symbol": "BTC", "side": "sell", "quantity": D('1.5')}]
    assert reservations(pending) == (D(0), {"BTC": D('1.5')})
    with pytest.raises(PortfolioError, match='holding'):
        validate_order({"cash_balance": D(2000)}, [{"symbol": "BTC", "quantity": D(2)}], pending, request(side='sell', quantity='1'), RiskSettings())


def test_investment_limits_include_fees_but_allow_exits():
    with pytest.raises(PortfolioError, match='Investment'):
        validate_order({"cash_balance": D(1000)}, [], [], request(), RiskSettings(max_investment=201))
    result = validate_order({"cash_balance": D(1000)}, [], [], request(), RiskSettings())
    assert result['stop_loss_price'] == 95 and result['take_profit_price'] == 110
    result = validate_order({"cash_balance": D(0)}, [{"symbol": "BTC", "quantity": D(2)}], [], request(side='sell'), RiskSettings(min_investment=500))
    assert result['stop_loss_price'] is None


def test_valuation_identity_and_missing_price_never_zero():
    p = {'portfolio_id': 1, 'initial_cash': D(1000), 'cash_balance': D(798), 'risk_settings': {}}
    h = [{'symbol': 'BTC', 'quantity': D(2), 'cost_basis': D(202), 'realized_pnl': D(0)}]
    now = datetime.now(timezone.utc)
    result = value_snapshot(p, h, [], {'BTC': (D(120), now)}, now)
    assert result['total_value'] == 1038
    assert result['total_pnl'] == result['total_value'] - p['initial_cash'] == 38
    assert result['cash_allocation_pct'] + result['holdings'][0]['allocation_pct'] == 100
    result = value_snapshot(p, h, [], {}, now)
    assert result['total_value'] is result['unrealized_pnl'] is result['total_pnl'] is None
    assert result['holdings'][0]['market_value'] is None
    assert result['available_cash'] == 798 and result['unpriced_symbols'] == ['BTC']
