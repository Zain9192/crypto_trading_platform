from __future__ import annotations

import math

import numpy as np
import talib

from app.market.schemas import IndicatorPoint, OhlcvCandle


def calculate_indicators(candles: list[OhlcvCandle]) -> list[IndicatorPoint]:
    """Use TA-Lib's standard warm-up periods; unavailable values are JSON null."""
    if not candles:
        return []
    closes = np.asarray([candle.close for candle in candles], dtype=np.float64)
    macd, signal, histogram = talib.MACD(closes, fastperiod=12, slowperiod=26, signalperiod=9)
    upper, middle, lower = talib.BBANDS(closes, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
    series = {
        "sma_20": talib.SMA(closes, timeperiod=20),
        "ema_20": talib.EMA(closes, timeperiod=20),
        "rsi_14": talib.RSI(closes, timeperiod=14),
        "macd": macd, "macd_signal": signal, "macd_histogram": histogram,
        "bb_middle": middle, "bb_upper": upper, "bb_lower": lower,
    }
    return [IndicatorPoint(
        timestamp=candle.timestamp, close=candle.close, volume=candle.volume,
        **{name: float(values[index]) if math.isfinite(values[index]) else None
           for name, values in series.items()},
    ) for index, candle in enumerate(candles)]
