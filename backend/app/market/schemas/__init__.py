from .market import (
    OHLCVSchema,
    PriceSchema,
    AssetSchema,
    IndicatorSchema,
)

# Backward-compatible aliases used by market services
MarketAsset = AssetSchema
OhlcvCandle = OHLCVSchema
IndicatorPoint = IndicatorSchema

SUPPORTED_INTERVALS = [
    "1m",
    "5m",
    "15m",
    "1h",
    "4h",
    "1d",
]

__all__ = [
    "OHLCVSchema",
    "PriceSchema",
    "AssetSchema",
    "IndicatorSchema",
    "MarketAsset",
    "OhlcvCandle",
    "IndicatorPoint",
    "SUPPORTED_INTERVALS",
]
