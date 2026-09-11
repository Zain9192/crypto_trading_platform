"""Runs against a disposable PostgreSQL service in CI, never the application database."""
import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from app.prediction.registry import PostgresRegistry

DSN = os.getenv("PREDICTION_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL test service is not configured")


def test_migration_registration_activation_and_forecast_persistence():
    with psycopg.connect(DSN) as connection:
        root = Path(__file__).resolve().parents[3] / "database" / "postgres"
        for name in ("001_initial.sql", "003_prediction.sql", "003_prediction.sql"):
            connection.execute((root / name).read_text())
    registry = PostgresRegistry(DSN)
    symbol = "T" + uuid4().hex[:10]
    records = [{"version": str(uuid4()), "symbol": symbol, "interval": "1d",
                "checksum": "a" * 64, "metadata": {"features": ["return_1"]}} for _ in range(2)]
    registry.register(records[0], activate=True)
    registry.register(records[1], activate=False)
    assert registry.active(symbol, "1d")["version"] == records[0]["version"]
    registry.activate(records[1]["version"])
    assert registry.active(symbol, "1d")["version"] == records[1]["version"]
    assert sum(record["is_active"] for record in registry.list_models(symbol, "1d")) == 1
    assert registry.version(records[0]["version"])["checksum"] == "a" * 64
    registry.record_prediction({"symbol": symbol, "interval": "1d", "predicted_price": 101,
                                "confidence": 0.6, "model_version": records[1]["version"]})
    with psycopg.connect(DSN) as connection:
        count = connection.execute("SELECT count(*) FROM predictions p JOIN crypto_assets a USING (asset_id) WHERE a.symbol = %s", (symbol,)).fetchone()[0]
        assert count == 1
    with pytest.raises(ValueError, match="Unknown"):
        registry.activate(str(uuid4()))
    assert registry.active(symbol, "1d")["version"] == records[1]["version"]
