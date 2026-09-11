from datetime import timedelta
from unittest.mock import Mock

import numpy as np
import pytest

from app.prediction.artifacts import ArtifactStore
from app.prediction.data import FEATURES, chronological_split, feature_frame, samples_from_frame
from app.prediction.service import ModelUnavailable, PredictionService
from app.prediction.training import train_version


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    # Fixture factory called by the test so the candle fixture remains isolated.
    return tmp_path_factory.mktemp("models")


def test_real_three_model_training_roundtrip_and_inference(candles, trained):
    artifacts = ArtifactStore(trained)
    registry = Mock()
    record = train_version(candles, artifacts, registry, lookback=5, epochs=1, trees=4, activate=True)
    registry.register.assert_called_once_with(record, activate=True)
    bundle, metadata = artifacts.load(record["version"], record["checksum"])
    frame = feature_frame(candles)
    train, _, _ = chronological_split(samples_from_frame(frame, 5))
    # Scaler must use only the chronological training windows, not validation/test.
    np.testing.assert_allclose(bundle.scaler.mean_, train.X.reshape(-1, len(FEATURES)).mean(axis=0), rtol=1e-5, atol=1e-7)
    assert set(metadata["metrics"]) == {"validation", "test"}
    assert metadata["metrics"]["test"]["ensemble"]["rmse"] >= 0
    assert metadata["backtest"]["execution"] == "one_bar_delayed_long_cash"
    registry.active.return_value = record
    market = Mock()
    market.get_history.return_value = candles
    service = PredictionService(market, registry, artifacts)
    now = candles[-1].timestamp + timedelta(days=1, hours=1)
    prediction = service.predict("BTC", "1d", now)
    assert prediction.model_version == record["version"]
    assert prediction.forecast_for > now
    assert 0.5 <= prediction.confidence <= 1
    assert prediction.predicted_price > 0
    registry.record_prediction.assert_called_once()
    with pytest.raises(ModelUnavailable, match="stale"):
        service.predict("BTC", "1d", now + timedelta(days=3))
    # Checksum validation must reject a corrupted artifact before deserialization.
    (artifacts.directory(record["version"]) / "forest.joblib").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        artifacts.load(record["version"], record["checksum"])


def test_artifact_path_cannot_escape_root(tmp_path):
    with pytest.raises(ValueError):
        ArtifactStore(tmp_path).directory("../../untrusted")
