from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.market.indicators import calculate_indicators
from app.market.schemas import OhlcvCandle


def test_calculate_indicators_returns_expected_fields() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = [
        OhlcvCandle(
            symbol="BTC",
            interval="1d",
            timestamp=start + timedelta(days=index),
            open=100 + index,
            high=102 + index,
            low=99 + index,
            close=101 + index,
            volume=1000 + index,
        )
        for index in range(40)
    ]

    points = calculate_indicators(candles)

    assert len(points) == 40
    assert points[19].sma_20 is not None
    assert points[-1].ema_20 is not None
    assert points[-1].rsi_14 == 100.0
    assert points[-1].macd is not None
    assert points[-1].macd_signal is not None
    assert points[-1].bb_upper is not None
    assert points[-1].bb_lower is not None
