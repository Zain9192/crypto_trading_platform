from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.market.dependencies import get_market_service
from app.market.providers import ProviderError
from app.market.schemas import MarketAsset, OhlcvCandle


@pytest.fixture
def market_client():
    service = Mock()
    service.get_top_assets.return_value = ([
        MarketAsset(id="bitcoin", symbol="BTC", name="Bitcoin", current_price=60000)
    ], False)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_market_service] = lambda: service
    try:
        with TestClient(app) as client:
            yield client, service
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_market_router_is_mounted_in_application(market_client):
    client, service = market_client
    response = client.get("/api/v1/market/assets")
    assert response.status_code == 200
    assert response.json()["items"][0]["current_price"] == 60000
    service.get_top_assets.assert_called_once_with(50)


@pytest.mark.parametrize("interval", ["1h", "4h", "1d", "1w", "1M"])
def test_all_planned_candle_intervals(market_client, interval):
    client, service = market_client
    service.get_ohlcv.return_value = ([OhlcvCandle(
        symbol="BTC", interval=interval, timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        open=10, high=12, low=9, close=11, volume=100,
    )], False)
    response = client.get(f"/api/v1/market/ohlcv/BTC?interval={interval}&limit=20")
    assert response.status_code == 200
    assert response.json()["items"][0]["interval"] == interval
    service.get_ohlcv.assert_called_once_with("BTC", interval, 20)


@pytest.mark.parametrize("query", ["limit=0", "limit=51"])
def test_invalid_market_limits_do_not_call_provider(market_client, query):
    client, service = market_client
    assert client.get(f"/api/v1/market/assets?{query}").status_code == 422
    service.get_top_assets.assert_not_called()


def test_provider_failure_returns_502(market_client):
    client, service = market_client
    service.get_top_assets.side_effect = ProviderError("Provider unavailable")
    response = client.get("/api/v1/market/assets")
    assert response.status_code == 502
    assert response.json()["detail"] == "Provider unavailable"


@pytest.mark.parametrize("query, expected_limit", [("", 50), ("?limit=3", 3),
                                                        ("?limit=invalid", 50), ("?limit=99", 50)])
def test_websocket_snapshot_and_disconnect(market_client, query, expected_limit):
    client, service = market_client
    with client.websocket_connect(f"/api/v1/market/ws/prices{query}") as socket:
        message = socket.receive_json()
        assert message["type"] == "market_snapshot"
        assert message["items"][0]["symbol"] == "BTC"
        assert message["refresh_seconds"] == 30
        assert datetime.fromisoformat(message["generated_at"]).tzinfo is not None
    service.get_top_assets.assert_called_once_with(expected_limit)


def test_websocket_reports_provider_error(market_client):
    client, service = market_client
    service.get_top_assets.side_effect = ProviderError("Provider unavailable")
    with client.websocket_connect("/api/v1/market/ws/prices") as socket:
        assert socket.receive_json() == {"type": "error", "detail": "Provider unavailable"}
