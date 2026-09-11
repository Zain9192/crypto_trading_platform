from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.market.schemas import OhlcvCandle


@pytest.fixture
def candles():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    i = np.arange(360)
    close = 100 * np.exp(0.0005 * i + 0.025 * np.sin(i / 3) + 0.01 * np.cos(i / 7))
    return [OhlcvCandle(
        symbol="BTC", interval="1d", timestamp=start + timedelta(days=int(j)),
        open=float(value), high=float(value * 1.01), low=float(value * 0.99),
        close=float(value), volume=float(1000 + 100 * np.cos(j / 4)),
    ) for j, value in enumerate(close)]
