from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from app.market.providers import ProviderError
from app.prediction.data import FEATURE_VERSION, FEATURES
from app.prediction.service import ModelUnavailable, PredictionService
from app.trading.execution import prediction_signal


def make_service(candles, up, expected, *, refreshed=None):
    bundle = Mock(lookback=5)
    bundle.forecast.return_value = (np.array([expected]), np.array([up]), None, None)
    metadata = {"symbol": "BTC", "interval": "1d", "feature_version": FEATURE_VERSION, "features": FEATURES,
                "quote_asset": "USDT", "provider": "binance", "data_end": candles[0].timestamp.isoformat(),
                "validation_absolute_error_p95": 0.02}
    registry, artifacts, market = Mock(), Mock(), Mock()
    registry.active.return_value = {"version": "v1", "checksum": "c"}
    artifacts.load.return_value = (bundle, metadata)
    market.get_history.side_effect = [candles, refreshed or candles]
    return PredictionService(market, registry, artifacts), market


def now_after(candles):
    return candles[-1].timestamp + timedelta(days=1, minutes=5)


@pytest.mark.parametrize("up, expected, direction, confidence", [
    (0.7, 0.01, "up", 0.7),
    (0.3, -0.01, "down", 0.7),
    (0.7, -0.01, "neutral", 0.5),
    (0.3, 0.01, "neutral", 0.5),
])
def test_direction_requires_classifier_and_forecast_to_agree(candles, up, expected, direction, confidence):
    service, _ = make_service(candles, up, expected)
    forecast = service.predict("BTC", "1d", now_after(candles))
    assert forecast.direction == direction
    assert forecast.confidence == pytest.approx(confidence)
    assert forecast.up_probability == pytest.approx(up)
    assert (forecast.predicted_price > forecast.current_price) == (expected > 0)


def test_neutral_forecast_holds(candles):
    service, _ = make_service(candles, 0.9, -0.01)
    now = now_after(candles)
    forecast = service.predict("BTC", "1d", now)
    config = SimpleNamespace(symbol="BTC/USD", interval="1d")
    assert prediction_signal(config, forecast, now).signal.value == "hold"


def test_partial_latest_candle_is_refreshed_before_forecasting(candles):
    end = candles[-1].timestamp + timedelta(days=1)
    stale = candles[:-1] + [candles[-1].model_copy(update={"fetched_at": end - timedelta(minutes=10)})]
    fresh = candles[:-1] + [candles[-1].model_copy(update={"fetched_at": end + timedelta(minutes=2)})]
    service, market = make_service(stale, 0.7, 0.01, refreshed=fresh)
    forecast = service.predict("BTC", "1d", now_after(candles))
    market.ingest_ohlcv.assert_called_once_with("BTC", "1d", 5)
    assert forecast.as_of == end


def test_complete_history_is_not_refetched(candles):
    service, market = make_service(candles, 0.7, 0.01)
    service.predict("BTC", "1d", now_after(candles))
    market.ingest_ohlcv.assert_not_called()


def test_unrefreshable_partial_candle_is_unavailable(candles):
    end = candles[-1].timestamp + timedelta(days=1)
    stale = candles[:-1] + [candles[-1].model_copy(update={"fetched_at": end - timedelta(minutes=10)})]
    service, market = make_service(stale, 0.7, 0.01)
    market.ingest_ohlcv.side_effect = ProviderError("down")
    with pytest.raises(ModelUnavailable, match="incomplete"):
        service.predict("BTC", "1d", now_after(candles))


def test_partial_candle_still_stale_after_refresh_is_not_forecast(candles):
    # If the provider still serves the pre-close snapshot, the forecast must not use it.
    end = candles[-1].timestamp + timedelta(days=1)
    stale = candles[:-1] + [candles[-1].model_copy(update={"fetched_at": end - timedelta(minutes=10)})]
    service, _ = make_service(stale, 0.7, 0.01, refreshed=stale)
    with pytest.raises(ModelUnavailable, match="stale"):
        service.predict("BTC", "1d", now_after(candles))
