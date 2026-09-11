from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

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


def test_indicator_warmup_and_known_linear_series():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = [OhlcvCandle(
        symbol="BTC", interval="1d", timestamp=start + timedelta(days=i),
        open=i + 1, high=i + 1, low=i + 1, close=i + 1, volume=100,
    ) for i in range(40)]
    points = calculate_indicators(candles)
    assert all(point.sma_20 is None for point in points[:19])
    assert all(point.macd is None for point in points[:33])
    assert points[-1].sma_20 == pytest.approx(30.5)
    assert points[-1].ema_20 == pytest.approx(30.5)
    assert points[-1].rsi_14 == 100
    assert points[-1].macd == pytest.approx(7)
    assert points[-1].bb_upper == pytest.approx(30.5 + 2 * (33.25 ** 0.5))
    assert 'null' in points[0].model_dump_json()
    assert 'NaN' not in points[0].model_dump_json()
