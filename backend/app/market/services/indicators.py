"""Compatibility helper for the auxiliary indicator route."""
import numpy as np
import pandas as pd
import talib


def calculate_indicators(candles: list[dict]) -> pd.DataFrame:
    close = np.asarray([candle["close"] for candle in candles], dtype=np.float64)
    macd, _, _ = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
    upper, _, lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2)
    return pd.DataFrame({
        "sma": talib.SMA(close, timeperiod=20),
        "ema": talib.EMA(close, timeperiod=20),
        "rsi": talib.RSI(close, timeperiod=14),
        "macd": macd, "bollinger_upper": upper, "bollinger_lower": lower,
    })
