from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.market import router
from app.market.dependencies import get_market_service
from app.market.schemas import IndicatorPoint, MarketAsset, OhlcvCandle


class FakeMarketService:
    def get_top_assets(self, limit: int = 50, force_refresh: bool = False):
        return [MarketAsset(id="bitcoin", symbol="BTC", name="Bitcoin", current_price=60000)], True

    def get_asset(self, symbol: str):
        if symbol.upper() == "BTC":
            return MarketAsset(id="bitcoin", symbol="BTC", name="Bitcoin", current_price=60000)
        return None

    def get_ohlcv(self, symbol: str, interval: str, limit: int = 200):
        return [
            OhlcvCandle(
                symbol=symbol.upper(),
                interval=interval,
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                open=1,
                high=2,
                low=0.5,
                close=1.5,
                volume=100,
            )
        ], False

    def get_indicators(self, symbol: str, interval: str, limit: int = 200):
        return [
            IndicatorPoint(
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                close=1.5,
                volume=100,
                sma_20=1.2,
            )
        ]


app = FastAPI()
app.include_router(router, prefix="/api/v1")
app.dependency_overrides[get_market_service] = lambda: FakeMarketService()
client = TestClient(app)


def test_market_assets_endpoint() -> None:
    response = client.get("/api/v1/market/assets?limit=10")

    assert response.status_code == 200
    assert response.json()["items"][0]["symbol"] == "BTC"
    assert response.json()["cached"] is True


def test_ohlcv_endpoint() -> None:
    response = client.get("/api/v1/market/ohlcv/BTC?interval=1d&limit=20")

    assert response.status_code == 200
    assert response.json()["items"][0]["close"] == 1.5


def test_indicators_endpoint() -> None:
    response = client.get("/api/v1/market/indicators/BTC?interval=1d&limit=20")

    assert response.status_code == 200
    assert response.json()["items"][0]["sma_20"] == 1.2


def test_unknown_asset_returns_404() -> None:
    response = client.get("/api/v1/market/assets/UNKNOWN")

    assert response.status_code == 404
