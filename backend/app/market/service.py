from __future__ import annotations

from pymongo.errors import PyMongoError

from app.market.cache import MarketCacheProtocol
from app.market.indicators import calculate_indicators
from app.market.providers import MarketSnapshotProvider, OhlcvProvider
from app.market.repository import MarketRepositoryProtocol
from app.market.schemas import IndicatorPoint, MarketAsset, MarketInterval, OhlcvCandle


class MarketService:
    def __init__(
        self,
        market_provider: MarketSnapshotProvider,
        ohlcv_provider: OhlcvProvider,
        repository: MarketRepositoryProtocol,
        cache: MarketCacheProtocol,
        market_cache_ttl_seconds: int = 25,
        ohlcv_cache_ttl_seconds: int = 60,
    ) -> None:
        self.market_provider = market_provider
        self.ohlcv_provider = ohlcv_provider
        self.repository = repository
        self.cache = cache
        self.market_cache_ttl_seconds = market_cache_ttl_seconds
        self.ohlcv_cache_ttl_seconds = ohlcv_cache_ttl_seconds

    def get_top_assets(self, limit: int = 50, force_refresh: bool = False) -> tuple[list[MarketAsset], bool]:
        if not force_refresh:
            cached = self.cache.get_top_assets(limit)
            if cached is not None:
                return cached, True

        assets = self.market_provider.fetch_top_assets(limit)
        self.cache.set_top_assets(assets, limit, self.market_cache_ttl_seconds)
        return assets, False

    def get_asset(self, symbol: str) -> MarketAsset | None:
        normalized = symbol.upper().strip()
        if not normalized:
            raise ValueError("Symbol is required")
        assets, _ = self.get_top_assets(50)
        return next((asset for asset in assets if asset.symbol.upper() == normalized), None)

    def get_ohlcv(self, symbol: str, interval: MarketInterval, limit: int = 200) -> tuple[list[OhlcvCandle], bool]:
        normalized = symbol.upper().strip()
        if not normalized:
            raise ValueError("Symbol is required")

        cached = self.cache.get_ohlcv(normalized, interval, limit)
        if cached is not None:
            return cached, True

        candles = self.ohlcv_provider.fetch_ohlcv(normalized, interval, limit)
        try:
            self.repository.upsert_ohlcv(candles)
        except PyMongoError:
            # Market data remains usable when persistence is temporarily unavailable.
            pass
        self.cache.set_ohlcv(normalized, interval, limit, candles, self.ohlcv_cache_ttl_seconds)
        return candles, False

    def get_indicators(self, symbol: str, interval: MarketInterval, limit: int = 200) -> list[IndicatorPoint]:
        fetch_limit = min(max(limit, 50), 1000)
        candles, _ = self.get_ohlcv(symbol, interval, fetch_limit)
        points = calculate_indicators(candles)
        return points[-limit:]
