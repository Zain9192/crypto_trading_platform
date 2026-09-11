from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Keep CPU training/inference bounded in CI and worker containers.
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "1")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from app.prediction.data import Samples


@dataclass
class ModelBundle:
    classifier: object
    regressor: object
    lstm: object
    scaler: StandardScaler
    target_scale: float
    lookback: int

    def forecast(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        shape = X.shape
        scaled = self.scaler.transform(X.reshape(-1, shape[-1])).reshape(shape).astype(np.float32)
        probability = self.classifier.predict_proba(scaled[:, -1, :])[:, 1]
        xgb_return = np.asarray(self.regressor.predict(scaled[:, -1, :]), dtype=float)
        lstm_return = np.asarray(self.lstm(scaled, training=False)).reshape(-1) * self.target_scale
        forecast = (xgb_return + lstm_return) / 2
        if not all(np.isfinite(values).all() for values in (probability, xgb_return, lstm_return, forecast)):
            raise ValueError("Model returned a non-finite forecast")
        return forecast, probability, xgb_return, lstm_return

    def save(self, directory: Path) -> None:
        joblib.dump({"classifier": self.classifier, "scaler": self.scaler,
                     "target_scale": self.target_scale, "lookback": self.lookback}, directory / "forest.joblib")
        self.regressor.save_model(directory / "xgboost.json")
        self.lstm.save(directory / "sequence.keras")

    @classmethod
    def load(cls, directory: Path) -> "ModelBundle":
        # Only operator-created, checksum-verified bundles are passed here by the artifact store.
        from tensorflow import keras
        from xgboost import XGBRegressor
        state = joblib.load(directory / "forest.joblib")
        regressor = XGBRegressor()
        regressor.load_model(directory / "xgboost.json")
        return cls(state["classifier"], regressor,
                   keras.models.load_model(directory / "sequence.keras", compile=False, safe_mode=True),
                   state["scaler"], state["target_scale"], state["lookback"])


def fit_models(train: Samples, *, epochs: int = 10, trees: int = 100, seed: int = 42) -> ModelBundle:
    from tensorflow import keras
    from xgboost import XGBRegressor

    keras.utils.set_random_seed(seed)
    shape = train.X.shape
    scaler = StandardScaler().fit(train.X.reshape(-1, shape[-1]))
    X = scaler.transform(train.X.reshape(-1, shape[-1])).reshape(shape).astype(np.float32)
    classifier = RandomForestClassifier(n_estimators=trees, max_depth=8, min_samples_leaf=5,
                                        class_weight="balanced", random_state=seed, n_jobs=1)
    classifier.fit(X[:, -1, :], (train.returns > 0).astype(int))
    regressor = XGBRegressor(n_estimators=trees, max_depth=3, learning_rate=0.05,
                             objective="reg:squarederror", random_state=seed, n_jobs=1)
    regressor.fit(X[:, -1, :], train.returns)
    target_scale = max(float(np.std(train.returns)), 1e-6)
    lstm = keras.Sequential([
        keras.layers.Input(shape=(shape[1], shape[2])),
        keras.layers.LSTM(16), keras.layers.Dense(8, activation="relu"), keras.layers.Dense(1),
    ])
    lstm.compile(optimizer=keras.optimizers.Adam(learning_rate=0.001, clipnorm=1.0), loss="mse")
    # Explicit chronological batches avoid implicit dataset shuffling and extra tf.data threads.
    for _ in range(epochs):
        for start in range(0, len(X), 32):
            lstm.train_on_batch(X[start:start + 32], (train.returns[start:start + 32] / target_scale).astype(np.float32))
    return ModelBundle(classifier, regressor, lstm, scaler, target_scale, shape[1])
