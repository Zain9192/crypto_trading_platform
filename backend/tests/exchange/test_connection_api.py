from unittest.mock import Mock
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.api.routes.exchange import get_exchange_service
from app.auth.dependencies import get_auth_service, get_current_user
from app.exchange.adapters import ExchangeFailure
from app.main import app


@pytest.fixture
def isolated():
    previous = app.dependency_overrides.copy()
    service = Mock()
    app.dependency_overrides[get_current_user] = lambda: {'user_id': 7}
    app.dependency_overrides[get_exchange_service] = lambda: service
    yield TestClient(app), service
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


def test_login_required(isolated):
    client, _ = isolated
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides[get_auth_service] = lambda: Mock()
    assert client.get('/api/v1/exchanges').status_code == 401


def test_validation_never_echoes_credentials(isolated):
    client, service = isolated
    secret = uuid4().hex
    response = client.post('/api/v1/exchanges', json={'exchange': 'invalid', 'label': 'Research', 'sandbox': True,
        'credentials': {'api_key': secret, 'api_secret': secret}, 'read_only': False})
    assert response.status_code == 422
    assert secret not in response.text
    service.create.assert_not_called()


def test_no_http_order_submission(isolated):
    client, service = isolated
    identity = uuid4()
    assert client.post(f'/api/v1/exchanges/{identity}/orders', json={}).status_code in (404,405)
    assert client.post(f'/api/v1/exchanges/{identity}/orders/o1/cancel').status_code in (404,405)
    service.read.assert_not_called()


def test_owner_and_safe_errors(isolated):
    client, service = isolated
    identity = uuid4()
    service.read.side_effect = ExchangeFailure('Exchange connection not found',404)
    assert client.get(f'/api/v1/exchanges/{identity}/balances').status_code == 404
    service.read.assert_called_once_with(7,identity,'get_balance')
    service.read.side_effect = ExchangeFailure('Exchange rate limit reached',429)
    assert client.get(f'/api/v1/exchanges/{identity}/balances').status_code == 429


def test_query_validation(isolated):
    client, service = isolated
    path = f'/api/v1/exchanges/{uuid4()}/trades'
    for query in ({'symbol':'BTC/USDT','limit':101}, {'symbol':'BTC/USDT','since':'2026-01-01T00:00:00'}, {'symbol':'BTC/USDT:USDT'}):
        assert client.get(path,params=query).status_code == 422
    service.read.assert_not_called()
