from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from app.market.schemas import MarketInterval
from app.prediction.artifacts import ArtifactStore
from app.prediction.data import DataError, FEATURES, FEATURE_VERSION, candle_end, feature_frame
from app.prediction.registry import Registry
from app.prediction.drift import assess
from app.prediction.schemas import Forecast, RankedForecast, RankingResponse


class ModelUnavailable(RuntimeError):
    pass


class PredictionService:
    def __init__(self, market, registry: Registry, artifacts: ArtifactStore) -> None:
        self.market = market
        self.registry = registry
        self.artifacts = artifacts

    def predict(self, symbol: str, interval: MarketInterval, now: datetime | None = None) -> Forecast:
        symbol = symbol.upper().strip()
        if not symbol.isalnum() or len(symbol) > 20:
            raise DataError("Invalid asset symbol")
        now = now or datetime.now(timezone.utc)
        record = self.registry.active(symbol, interval)
        if record is None:
            raise ModelUnavailable("No active model; train and explicitly activate a version first")
        try:
            bundle, metadata = self.artifacts.load(record["version"], record["checksum"])
        except (ValueError, OSError, KeyError) as exc:
            raise ModelUnavailable("Model artifacts unavailable or incompatible; verify runtime and retrain") from exc
        if (metadata["symbol"] != symbol or metadata["interval"] != interval or
            metadata["feature_version"] != FEATURE_VERSION or metadata["features"] != FEATURES):
            raise ModelUnavailable("Model feature or asset contract does not match")
        candles = self.market.get_history(symbol, interval, 1000)
        frame = feature_frame(candles, now)
        if candles[0].quote_asset != metadata["quote_asset"] or candles[0].provider != metadata["provider"]:
            raise DataError("History quote asset or provider does not match the model")
        if len(frame) < bundle.lookback:
            raise DataError("Insufficient current history for model lookback")
        source_open = frame.index[-1].to_pydatetime()
        as_of = candle_end(source_open, interval)
        forecast_for = candle_end(as_of, interval)
        if now >= forecast_for:
            raise ModelUnavailable("Stored history is stale; refresh ingestion before requesting a forecast")
        if source_open < datetime.fromisoformat(metadata["data_end"]):
            raise ModelUnavailable("Input history predates the model's evaluated data")
        X = frame[FEATURES].to_numpy(dtype=np.float32)[-bundle.lookback:][None, :, :]
        returns, probability, _, _ = bundle.forecast(X)
        expected, up = float(returns[0]), float(probability[0])
        if expected <= -1:
            raise ModelUnavailable("Forecast implies a non-positive price; model requires review")
        price = float(frame.close.iloc[-1])
        result = Forecast(
            symbol=symbol, interval=interval, quote_asset=metadata["quote_asset"], model_version=record["version"],
            as_of=as_of, forecast_for=forecast_for, generated_at=now,
            current_price=price, predicted_price=price * (1 + expected),
            direction="up" if up >= 0.5 else "down", up_probability=up, confidence=max(up, 1 - up),
            expected_return=expected, estimated_risk=float(frame.return_1.tail(20).std()),
            validation_error_p95=metadata["validation_absolute_error_p95"],
            drift=assess(frame[FEATURES].to_numpy(dtype=float)[-120:], FEATURES, metadata.get("drift_baseline")),
        )
        self.registry.record_prediction(result.model_dump(mode="json"))
        return result

    def rank(self, symbols: list[str], interval: MarketInterval) -> RankingResponse:
        items, unavailable = [], {}
        for symbol in dict.fromkeys(value.upper().strip() for value in symbols):
            try:
                forecast = self.predict(symbol, interval)
            except (ModelUnavailable, DataError) as exc:
                unavailable[symbol] = str(exc)
                continue
            score = forecast.expected_return * forecast.up_probability / max(forecast.estimated_risk, 1e-6)
            items.append(RankedForecast(forecast=forecast, score=score))
        items.sort(key=lambda item: (-item.score, item.forecast.symbol))
        return RankingResponse(items=items, unavailable=unavailable)
