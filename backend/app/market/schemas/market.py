from datetime import datetime
from pydantic import BaseModel


class OHLCVSchema(BaseModel):
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    timeframe: str


class PriceSchema(BaseModel):
    symbol: str
    price: float
    timestamp: datetime


class AssetSchema(BaseModel):
    symbol: str
    name: str
    price: float
    market_cap: float | None = None


class IndicatorSchema(BaseModel):
    symbol: str
    timeframe: str
    sma: float | None = None
    ema: float | None = None
    rsi: float | None = None
    macd: float | None = None
    bollinger_upper: float | None = None
    bollinger_lower: float | None = None
