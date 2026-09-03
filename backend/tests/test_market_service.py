from __future__ import annotations

from datetime import datetime, timezone

from app.market.schemas import MarketAsset, OhlcvCandle
from app.market.service import MarketService


class FakeMarketProvider:
    def __init__(self) -> None:
        self.calls = 0

    def fetch_top_assets(self, limit: int) -> list[MarketAsset]:
        self.calls += 1
        return [MarketAsset(id="bitcoin", symbol="BTC", name="Bitcoin", current_price=60000)] * limit


class FakeOhlcvProvider:
    def __init__(self) -> None:
        self.calls = 0

    def fetch_ohlcv(self, symbol: str, interval: str, limit: int) -> list[OhlcvCandle]:
        self.calls += 1
        return [
            OhlcvCandle(
                symbol=symbol,
                interval=interval,
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                open=1,
                high=2,
                low=0.5,
                close=1.5,
                volume=100,
            )
        ]


class FakeRepository:
    def __init__(self) -> None:
        self.saved: list[OhlcvCandle] = []

    def upsert_ohlcv(self, candles: list[OhlcvCandle]) -> None:
        self.saved.extend(candles)

    def get_ohlcv(self, symbol: str, interval: str, limit: int) -> list[OhlcvCandle]:
        return self.saved[-limit:]


class FakeCache:
    def __init__(self) -> None:
        self.assets = None
        self.candles = None

    def get_top_assets(self, limit: int):
        return self.assets

    def set_top_assets(self, assets, limit: int, ttl_seconds: int) -> None:
        self.assets = assets

    def get_ohlcv(self, symbol: str, interval: str, limit: int):
        return self.candles

    def set_ohlcv(self, symbol: str, interval: str, limit: int, candles, ttl_seconds: int) -> None:
        self.candles = candles


def test_market_service_uses_cache_after_first_market_request() -> None:
    market_provider = FakeMarketProvider()
    service = MarketService(market_provider, FakeOhlcvProvider(), FakeRepository(), FakeCache())

    first, first_cached = service.get_top_assets(2)
    second, second_cached = service.get_top_assets(2)

    assert len(first) == 2
    assert len(second) == 2
    assert first_cached is False
    assert second_cached is True
    assert market_provider.calls == 1


def test_market_service_persists_and_caches_ohlcv() -> None:
    ohlcv_provider = FakeOhlcvProvider()
    repository = FakeRepository()
    cache = FakeCache()
    service = MarketService(FakeMarketProvider(), ohlcv_provider, repository, cache)

    first, first_cached = service.get_ohlcv("BTC", "1d", 20)
    second, second_cached = service.get_ohlcv("BTC", "1d", 20)

    assert first_cached is False
    assert second_cached is True
    assert ohlcv_provider.calls == 1
    assert len(repository.saved) == 1
    assert first[0].symbol == "BTC"
    assert second[0].close == 1.5
