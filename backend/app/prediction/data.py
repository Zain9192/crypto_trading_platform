from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app.market.indicators import calculate_indicators
from app.market.schemas import MarketInterval, OhlcvCandle

FEATURE_VERSION = "ohlcv-v1"
FEATURES = ["return_1", "return_3", "return_6", "volatility_20", "volume_ratio", "range_ratio",
            "sma_ratio", "ema_ratio", "rsi", "macd_ratio", "bb_width"]


class DataError(ValueError):
    pass


def candle_end(timestamp: datetime, interval: MarketInterval) -> datetime:
    offset = {"1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4),
              "1d": pd.Timedelta(days=1), "1w": pd.Timedelta(weeks=1), "1M": pd.DateOffset(months=1)}[interval]
    return (pd.Timestamp(timestamp) + offset).to_pydatetime()


def feature_frame(candles: list[OhlcvCandle], now: datetime | None = None) -> pd.DataFrame:
    if not candles:
        raise DataError("No stored candles; run market ingestion first")
    now = now or datetime.now(timezone.utc)
    candles = sorted(candles, key=lambda c: pd.Timestamp(c.timestamp).tz_localize("UTC")
                     if c.timestamp.tzinfo is None else pd.Timestamp(c.timestamp))
    identity = {(c.symbol, c.interval, c.quote_asset, c.provider) for c in candles}
    if len(identity) != 1:
        raise DataError("Training history must contain one symbol, interval, quote asset and provider")
    closed = []
    for candle in candles:
        timestamp = pd.Timestamp(candle.timestamp)
        timestamp = timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")
        if candle_end(timestamp.to_pydatetime(), candle.interval) <= now:
            closed.append(candle.model_copy(update={"timestamp": timestamp.to_pydatetime()}))
    if len(closed) < 60:
        raise DataError("At least 60 closed candles are required for feature warm-up")
    for previous, current in zip(closed, closed[1:]):
        if current.timestamp != candle_end(previous.timestamp, previous.interval):
            raise DataError("Stored candles contain duplicates or gaps; ingest continuous history")
    frame = pd.DataFrame([c.model_dump() for c in closed]).set_index("timestamp")
    numeric = frame[["open", "high", "low", "close", "volume"]].to_numpy(dtype=float)
    if not np.isfinite(numeric).all() or (numeric[:, :4] <= 0).any() or (numeric[:, 4] < 0).any():
        raise DataError("Candles must contain finite positive prices and nonnegative volume")
    if ((frame.high < frame[["open", "close"]].max(axis=1)) |
        (frame.low > frame[["open", "close"]].min(axis=1)) | (frame.low > frame.high)).any():
        raise DataError("OHLC bounds are inconsistent")
    indicators = pd.DataFrame([point.model_dump() for point in calculate_indicators(closed)], index=frame.index)
    close = frame.close
    frame["return_1"] = close.pct_change()
    frame["return_3"] = close.pct_change(3)
    frame["return_6"] = close.pct_change(6)
    frame["volatility_20"] = frame.return_1.rolling(20).std()
    frame["volume_ratio"] = frame.volume / frame.volume.rolling(20).mean().replace(0, np.nan)
    frame["range_ratio"] = (frame.high - frame.low) / close
    frame["sma_ratio"] = close / indicators.sma_20 - 1
    frame["ema_ratio"] = close / indicators.ema_20 - 1
    frame["rsi"] = indicators.rsi_14 / 100
    frame["macd_ratio"] = indicators.macd / close
    frame["bb_width"] = (indicators.bb_upper - indicators.bb_lower) / close
    frame[FEATURES] = frame[FEATURES].replace([np.inf, -np.inf], np.nan)
    # Drop only the leading warm-up. Interior invalid values must not hide gaps.
    valid = frame[FEATURES].notna().all(axis=1)
    if not valid.any():
        raise DataError("No usable feature rows")
    frame = frame.loc[valid[valid].index[0]:]
    if frame[FEATURES].isna().any().any():
        raise DataError("Invalid feature values after warm-up")
    return frame


@dataclass
class Samples:
    X: np.ndarray
    returns: np.ndarray
    prices: np.ndarray
    next_prices: np.ndarray
    times: list[datetime]
    target_times: list[datetime]

    def subset(self, start: int, end: int | None = None) -> "Samples":
        return Samples(self.X[start:end], self.returns[start:end], self.prices[start:end],
                       self.next_prices[start:end], self.times[start:end], self.target_times[start:end])


def samples_from_frame(frame: pd.DataFrame, lookback: int = 20) -> Samples:
    if not 2 <= lookback <= 120:
        raise DataError("Lookback must be between 2 and 120")
    features = frame[FEATURES].to_numpy(dtype=np.float32)
    ends = list(range(lookback - 1, len(frame) - 1))
    if not ends:
        raise DataError("Insufficient history for sequences")
    prices = frame.close.to_numpy(dtype=float)
    return Samples(
        np.asarray([features[i - lookback + 1:i + 1] for i in ends]),
        np.asarray([prices[i + 1] / prices[i] - 1 for i in ends]),
        prices[ends], prices[np.asarray(ends) + 1],
        [frame.index[i].to_pydatetime() for i in ends],
        [frame.index[i + 1].to_pydatetime() for i in ends],
    )


def chronological_split(samples: Samples) -> tuple[Samples, Samples, Samples]:
    if len(samples.X) < 200:
        raise DataError("At least 200 supervised sequences are required; ingest at least 300 candles")
    a, b = int(len(samples.X) * 0.7), int(len(samples.X) * 0.85)
    train, validation, test = samples.subset(0, a - 1), samples.subset(a, b - 1), samples.subset(b)
    if train.target_times[-1] >= validation.times[0] or validation.target_times[-1] >= test.times[0]:
        raise DataError("Split label windows overlap")
    if len(np.unique(train.returns > 0)) < 2:
        raise DataError("Training history must contain both rising and falling targets")
    return train, validation, test
