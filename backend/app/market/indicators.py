from __future__ import annotations

from math import sqrt

from app.market.schemas import IndicatorPoint, OhlcvCandle


def _sma(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if period <= 0:
        return result
    rolling_sum = 0.0
    for index, value in enumerate(values):
        rolling_sum += value
        if index >= period:
            rolling_sum -= values[index - period]
        if index >= period - 1:
            result[index] = rolling_sum / period
    return result


def _ema(values: list[float], period: int) -> list[float | None]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    ema_values: list[float | None] = [None] * len(values)
    current = values[0]
    for index, value in enumerate(values):
        if index == 0:
            current = value
        else:
            current = (value - current) * multiplier + current
        ema_values[index] = current
    return ema_values


def _rsi(values: list[float], period: int = 14) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return result

    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, period + 1):
        change = values[index] - values[index - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    average_gain = sum(gains) / period
    average_loss = sum(losses) / period

    def to_rsi(avg_gain: float, avg_loss: float) -> float:
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    result[period] = to_rsi(average_gain, average_loss)
    for index in range(period + 1, len(values)):
        change = values[index] - values[index - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        average_gain = ((average_gain * (period - 1)) + gain) / period
        average_loss = ((average_loss * (period - 1)) + loss) / period
        result[index] = to_rsi(average_gain, average_loss)
    return result


def _bollinger(values: list[float], period: int = 20, deviations: float = 2.0) -> tuple[list[float | None], list[float | None], list[float | None]]:
    middle = _sma(values, period)
    upper: list[float | None] = [None] * len(values)
    lower: list[float | None] = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = values[index - period + 1 : index + 1]
        mean = middle[index]
        if mean is None:
            continue
        variance = sum((value - mean) ** 2 for value in window) / period
        stddev = sqrt(variance)
        upper[index] = mean + deviations * stddev
        lower[index] = mean - deviations * stddev
    return middle, upper, lower


def calculate_indicators(candles: list[OhlcvCandle]) -> list[IndicatorPoint]:
    if not candles:
        return []

    closes = [candle.close for candle in candles]
    sma_20 = _sma(closes, 20)
    ema_20 = _ema(closes, 20)
    rsi_14 = _rsi(closes, 14)
    ema_12 = _ema(closes, 12)
    ema_26 = _ema(closes, 26)
    macd_values = [
        (fast - slow) if fast is not None and slow is not None else None
        for fast, slow in zip(ema_12, ema_26, strict=True)
    ]
    macd_numeric = [value if value is not None else 0.0 for value in macd_values]
    macd_signal = _ema(macd_numeric, 9)
    bb_middle, bb_upper, bb_lower = _bollinger(closes, 20, 2.0)

    points: list[IndicatorPoint] = []
    for index, candle in enumerate(candles):
        macd = macd_values[index]
        signal = macd_signal[index]
        points.append(
            IndicatorPoint(
                timestamp=candle.timestamp,
                close=candle.close,
                volume=candle.volume,
                sma_20=sma_20[index],
                ema_20=ema_20[index],
                rsi_14=rsi_14[index],
                macd=macd,
                macd_signal=signal,
                macd_histogram=(macd - signal) if macd is not None and signal is not None else None,
                bb_middle=bb_middle[index],
                bb_upper=bb_upper[index],
                bb_lower=bb_lower[index],
            )
        )
    return points
