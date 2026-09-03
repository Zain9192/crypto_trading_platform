from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

MarketInterval = Literal["1h", "4h", "1d", "1w", "1M"]
SUPPORTED_INTERVALS: tuple[MarketInterval, ...] = ("1h", "4h", "1d", "1w", "1M")


class MarketAsset(BaseModel):
    id: str
    symbol: str
    name: str
    image: str | None = None
    current_price: float | None = None
    market_cap: float | None = None
    market_cap_rank: int | None = None
    total_volume: float | None = None
    high_24h: float | None = None
    low_24h: float | None = None
    price_change_percentage_24h: float | None = None
    circulating_supply: float | None = None
    last_updated: datetime | None = None


class MarketAssetsResponse(BaseModel):
    items: list[MarketAsset]
    count: int
    cached: bool
    refresh_seconds: int
    source: str = "coingecko"


class OhlcvCandle(BaseModel):
    symbol: str
    interval: MarketInterval
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_asset: str = "USDT"
    provider: str = "binance"


class OhlcvResponse(BaseModel):
    symbol: str
    interval: MarketInterval
    items: list[OhlcvCandle]
    count: int
    cached: bool
    source: str = "binance"


class IndicatorPoint(BaseModel):
    timestamp: datetime
    close: float
    volume: float
    sma_20: float | None = None
    ema_20: float | None = None
    rsi_14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    bb_middle: float | None = None
    bb_upper: float | None = None
    bb_lower: float | None = None


class IndicatorResponse(BaseModel):
    symbol: str
    interval: MarketInterval
    items: list[IndicatorPoint]
    count: int
    source: str = "calculated"


class MarketStreamMessage(BaseModel):
    type: Literal["market_snapshot"] = "market_snapshot"
    generated_at: datetime
    refresh_seconds: int = Field(ge=1)
    items: list[MarketAsset]
