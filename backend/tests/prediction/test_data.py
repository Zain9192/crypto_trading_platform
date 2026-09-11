from datetime import timedelta

import numpy as np
import pytest

from app.prediction.data import (DataError, FEATURES, chronological_split, feature_frame, samples_from_frame)


def test_features_do_not_change_when_future_prices_change(candles):
    original = feature_frame(candles)
    future = [c.model_copy(update={"open": c.open * 2, "high": c.high * 2,
                                 "low": c.low * 2, "close": c.close * 2}) for c in candles[250:]]
    changed = feature_frame(candles[:250] + future)
    np.testing.assert_allclose(original[FEATURES].iloc[:200], changed[FEATURES].iloc[:200])


def test_chronological_splits_purge_boundary_labels(candles):
    samples = samples_from_frame(feature_frame(candles), 10)
    train, validation, test = chronological_split(samples)
    assert train.target_times[-1] < validation.times[0]
    assert validation.target_times[-1] < test.times[0]
    assert train.times[0] < validation.times[0] < test.times[0]
    np.testing.assert_allclose(samples.returns, samples.next_prices / samples.prices - 1)


def test_unclosed_candles_are_excluded(candles):
    now = candles[-1].timestamp + timedelta(hours=12)
    frame = feature_frame(candles, now)
    assert frame.index[-1] == candles[-2].timestamp


@pytest.mark.parametrize("kind", ["gap", "duplicate", "bad_price", "mixed_quote"])
def test_bad_history_is_rejected(candles, kind):
    if kind == "gap":
        candles.pop(100)
    elif kind == "duplicate":
        candles.insert(100, candles[100])
    elif kind == "bad_price":
        candles[100] = candles[100].model_copy(update={"close": float("nan")})
    else:
        candles[100] = candles[100].model_copy(update={"quote_asset": "EUR"})
    with pytest.raises(DataError):
        feature_frame(candles)


def test_too_little_training_history_is_rejected(candles):
    with pytest.raises(DataError, match="200 supervised"):
        chronological_split(samples_from_frame(feature_frame(candles[:150])))


def test_default_ingestion_window_supports_training(candles):
    from app.core.config import Settings
    configured_history = candles[:Settings().market_history_candle_limit]
    train, validation, test = chronological_split(samples_from_frame(feature_frame(configured_history)))
    assert len(train.X) > len(validation.X) > 0
    assert len(test.X) > 0


@pytest.mark.parametrize("timestamp, interval, expected", [
    ("2024-02-01T00:00:00+00:00", "1M", "2024-03-01T00:00:00+00:00"),
    ("2024-12-01T00:00:00+00:00", "1M", "2025-01-01T00:00:00+00:00"),
    ("2024-02-28T00:00:00+00:00", "1d", "2024-02-29T00:00:00+00:00"),
    ("2024-01-01T00:00:00+00:00", "1w", "2024-01-08T00:00:00+00:00"),
    ("2024-01-01T00:00:00+00:00", "4h", "2024-01-01T04:00:00+00:00"),
    ("2024-01-01T00:00:00+00:00", "1h", "2024-01-01T01:00:00+00:00"),
])
def test_candle_end_preserves_calendar_boundaries_without_deprecations(timestamp, interval, expected):
    from datetime import datetime
    import warnings
    from app.prediction.data import candle_end
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        assert candle_end(datetime.fromisoformat(timestamp), interval).isoformat() == expected
