from datetime import datetime, timezone


async def normalize_ohlcv(symbol: str, timeframe: str, candles: list):
    normalized = []

    for candle in candles:
        normalized.append(
            {
                "symbol": symbol,
                "timestamp": datetime.fromtimestamp(
                    candle[0] / 1000,
                    tz=timezone.utc,
                ),
                "open": candle[1],
                "high": candle[2],
                "low": candle[3],
                "close": candle[4],
                "volume": candle[5] if len(candle) > 5 else 0,
                "timeframe": timeframe,
            }
        )

    return normalized
