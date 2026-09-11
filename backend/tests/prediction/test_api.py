from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_auth_service, get_current_user
from app.main import app
from app.prediction.dependencies import get_prediction_service
from app.prediction.schemas import Forecast
from app.prediction.service import ModelUnavailable, PredictionService


@pytest.fixture
def api():
    original = app.dependency_overrides.copy()
    service = Mock()
    app.dependency_overrides[get_current_user] = lambda: {"user_id": 1, "role": "trader"}
    app.dependency_overrides[get_prediction_service] = lambda: service
    try:
        with TestClient(app) as client:
            yield client, service
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)


def forecast(symbol="BTC", expected=0.01):
    now = datetime.now(timezone.utc)
    return Forecast(symbol=symbol, interval="1d", quote_asset="USDT", model_version="test",
                    as_of=now, forecast_for=now + timedelta(days=1), generated_at=now,
                    current_price=100, predicted_price=101, direction="up", up_probability=0.6,
                    confidence=0.6, expected_return=expected, estimated_risk=0.02, validation_error_p95=0.04)


def test_prediction_is_mounted_and_validated(api):
    client, service = api
    service.predict.return_value = forecast()
    response = client.get("/api/v1/predictions/BTC?interval=1d")
    assert response.status_code == 200
    assert response.json()["confidence_kind"] == "uncalibrated_random_forest_probability"
    assert client.get("/api/v1/predictions/BTC?interval=bad").status_code == 422


def test_no_active_model_returns_explicit_unavailable(api):
    client, service = api
    service.predict.side_effect = ModelUnavailable("No active model")
    assert client.get("/api/v1/predictions/BTC").status_code == 503


def test_anonymous_cannot_request_forecasts(api):
    client, _ = api
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides[get_auth_service] = lambda: Mock()
    assert client.get("/api/v1/predictions/BTC").status_code == 401


def test_ranking_orders_assets_and_reports_missing_models():
    service = PredictionService(Mock(), Mock(), Mock())
    service.predict = Mock(side_effect=[forecast("BTC", 0.01), forecast("ETH", 0.03), ModelUnavailable("No active model")])
    result = service.rank(["BTC", "ETH", "UNKNOWN", "BTC"], "1d")
    assert [item.forecast.symbol for item in result.items] == ["ETH", "BTC"]
    assert result.unavailable == {"UNKNOWN": "No active model"}
    assert service.predict.call_count == 3
