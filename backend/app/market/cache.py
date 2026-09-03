from __future__ import annotations

import json
from typing import Protocol

from redis import Redis
from redis.exceptions import RedisError

from app.market.schemas import MarketAsset, MarketInterval, OhlcvCandle


class MarketCacheProtocol(Protocol):
    def get_top_assets(self, limit: int) -> list[MarketAsset] | None: ...
    def set_top_assets(self, assets: list[MarketAsset], limit: int, ttl_seconds: int) -> None: ...
    def get_ohlcv(self, symbol: str, interval: MarketInterval, limit: int) -> list[OhlcvCandle] | None: ...
    def set_ohlcv(self, symbol: str, interval: MarketInterval, limit: int, candles: list[OhlcvCandle], ttl_seconds: int) -> None: ...


class RedisMarketCache:
    def __init__(self, client: Redis) -> None:
        self.client = client

    @staticmethod
    def _top_key(limit: int) -> str:
        return f"market:top:{limit}"

    @staticmethod
    def _ohlcv_key(symbol: str, interval: MarketInterval, limit: int) -> str:
        return f"market:ohlcv:{symbol.upper()}:{interval}:{limit}"

    def get_top_assets(self, limit: int) -> list[MarketAsset] | None:
        try:
            raw = self.client.get(self._top_key(limit))
        except RedisError:
            return None
        if not raw:
            return None
        try:
            payload = json.loads(raw)
            return [MarketAsset.model_validate(item) for item in payload]
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    def set_top_assets(self, assets: list[MarketAsset], limit: int, ttl_seconds: int) -> None:
        payload = json.dumps([asset.model_dump(mode="json") for asset in assets])
        try:
            pipeline = self.client.pipeline()
            pipeline.setex(self._top_key(limit), ttl_seconds, payload)
            for asset in assets:
                pipeline.setex(
                    f"market:latest:{asset.symbol.upper()}",
                    ttl_seconds,
                    json.dumps(asset.model_dump(mode="json")),
                )
            pipeline.execute()
        except RedisError:
            return

    def get_ohlcv(self, symbol: str, interval: MarketInterval, limit: int) -> list[OhlcvCandle] | None:
        try:
            raw = self.client.get(self._ohlcv_key(symbol, interval, limit))
        except RedisError:
            return None
        if not raw:
            return None
        try:
            payload = json.loads(raw)
            return [OhlcvCandle.model_validate(item) for item in payload]
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    def set_ohlcv(self, symbol: str, interval: MarketInterval, limit: int, candles: list[OhlcvCandle], ttl_seconds: int) -> None:
        payload = json.dumps([candle.model_dump(mode="json") for candle in candles])
        try:
            self.client.setex(self._ohlcv_key(symbol, interval, limit), ttl_seconds, payload)
        except RedisError:
            return
