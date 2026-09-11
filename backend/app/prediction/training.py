from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import uuid4

import numpy as np

from app.market.schemas import OhlcvCandle
from app.prediction.artifacts import ArtifactStore
from app.prediction.data import FEATURES, FEATURE_VERSION, chronological_split, feature_frame, samples_from_frame
from app.prediction.evaluation import backtest, evaluate
from app.prediction.models import fit_models
from app.prediction.registry import Registry


def train_version(candles: list[OhlcvCandle], artifacts: ArtifactStore, registry: Registry, *,
                  lookback: int = 20, epochs: int = 10, trees: int = 100,
                  seed: int = 42, fee_bps: float = 10, activate: bool = False,
                  now: datetime | None = None) -> dict:
    if not 1 <= epochs <= 100 or not 2 <= trees <= 1000:
        raise ValueError("Epochs must be 1..100 and trees 2..1000")
    if not 0 <= fee_bps <= 1000:
        raise ValueError("Fee must be between 0 and 1000 basis points")
    frame = feature_frame(candles, now)
    samples = samples_from_frame(frame, lookback)
    train, validation, test = chronological_split(samples)
    bundle = fit_models(train, epochs=epochs, trees=trees, seed=seed)
    results = {}
    for name, split in (("validation", validation), ("test", test)):
        forecast, probability, xgb, lstm = bundle.forecast(split.X)
        results[name] = {
            "ensemble": evaluate(split.returns, forecast, probability, split.prices),
            "xgboost": evaluate(split.returns, xgb, probability, split.prices),
            "lstm": evaluate(split.returns, lstm, probability, split.prices),
        }
    val_forecast, _, _, _ = bundle.forecast(validation.X)
    test_forecast, test_probability, _, _ = bundle.forecast(test.X)
    version = str(uuid4())
    metadata = {
        "symbol": candles[0].symbol, "interval": candles[0].interval,
        "quote_asset": candles[0].quote_asset, "provider": candles[0].provider,
        "feature_version": FEATURE_VERSION, "features": FEATURES, "lookback": lookback,
        "horizon_candles": 1, "seed": seed, "epochs": epochs, "trees": trees,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data_end": frame.index[-1].isoformat(),
        "dataset_sha256": hashlib.sha256(frame[["open", "high", "low", "close", "volume"]].to_csv().encode()).hexdigest(),
        "splits": {name: {"count": len(split.X), "first_feature_at": split.times[0].isoformat(),
                            "last_target_at": split.target_times[-1].isoformat()}
                   for name, split in (("train", train), ("validation", validation), ("test", test))},
        "validation_absolute_error_p95": float(np.quantile(np.abs(validation.returns - val_forecast), 0.95)),
        "metrics": results,
        "backtest": backtest(test.returns, test_forecast, test_probability, fee_bps),
        "confidence_kind": "uncalibrated_random_forest_probability",
    }
    checksum = artifacts.save(version, bundle, metadata)
    record = {"version": version, "symbol": candles[0].symbol, "interval": candles[0].interval,
              "checksum": checksum, "metadata": metadata}
    registry.register(record, activate=activate)
    return record
