from __future__ import annotations

from typing import Protocol

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class Registry(Protocol):
    def register(self, record: dict, activate: bool = False) -> None: ...
    def active(self, symbol: str, interval: str) -> dict | None: ...
    def activate(self, version: str) -> None: ...
    def version(self, version: str) -> dict | None: ...
    def list_models(self, symbol: str, interval: str) -> list[dict]: ...
    def record_prediction(self, forecast: dict) -> None: ...


class PostgresRegistry:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def register(self, record: dict, activate: bool = False) -> None:
        with psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=5) as connection:
            connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                               (record["symbol"] + ":" + record["interval"],))
            if activate:
                connection.execute("UPDATE ml_models SET is_active = FALSE WHERE symbol = %s AND timeframe = %s",
                                   (record["symbol"], record["interval"]))
            connection.execute(
                """INSERT INTO ml_models
                   (algorithm, model_version, symbol, timeframe, artifact_checksum, metadata, is_active)
                   VALUES ('rf_xgb_lstm', %s, %s, %s, %s, %s, %s)""",
                (record["version"], record["symbol"], record["interval"], record["checksum"],
                 Jsonb(record["metadata"]), activate),
            )

    def version(self, version: str) -> dict | None:
        with psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=5) as connection:
            return connection.execute(
                """SELECT model_version AS version, symbol, timeframe AS interval,
                   artifact_checksum AS checksum, metadata FROM ml_models
                   WHERE algorithm = 'rf_xgb_lstm' AND model_version = %s""", (version,),
            ).fetchone()

    def activate(self, version: str) -> None:
        with psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=5) as connection:
            record = connection.execute(
                "SELECT symbol, timeframe FROM ml_models WHERE algorithm = 'rf_xgb_lstm' AND model_version = %s",
                (version,),
            ).fetchone()
            if record is None:
                raise ValueError("Unknown model version")
            connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                               (record["symbol"] + ":" + record["timeframe"],))
            connection.execute("UPDATE ml_models SET is_active = FALSE WHERE symbol = %s AND timeframe = %s",
                               (record["symbol"], record["timeframe"]))
            connection.execute("UPDATE ml_models SET is_active = TRUE WHERE algorithm = 'rf_xgb_lstm' AND model_version = %s",
                               (version,))

    def active(self, symbol: str, interval: str) -> dict | None:
        with psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=5) as connection:
            return connection.execute(
                """SELECT model_version AS version, artifact_checksum AS checksum, metadata
                   FROM ml_models WHERE symbol = %s AND timeframe = %s AND is_active""",
                (symbol, interval),
            ).fetchone()

    def list_models(self, symbol: str, interval: str) -> list[dict]:
        with psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=5) as connection:
            return connection.execute(
                """SELECT model_version AS version, algorithm, trained_at, is_active, metadata
                   FROM ml_models WHERE symbol = %s AND timeframe = %s ORDER BY trained_at DESC LIMIT 50""",
                (symbol, interval),
            ).fetchall()

    def record_prediction(self, forecast: dict) -> None:
        with psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=5) as connection:
            asset = connection.execute(
                """INSERT INTO crypto_assets (symbol, name) VALUES (%s, %s)
                   ON CONFLICT (symbol) DO UPDATE SET symbol = EXCLUDED.symbol RETURNING asset_id""",
                (forecast["symbol"], forecast["symbol"]),
            ).fetchone()
            connection.execute(
                """INSERT INTO predictions (asset_id, model_id, timeframe, predicted_price, confidence, details)
                   SELECT %s, model_id, %s, %s, %s, %s FROM ml_models
                   WHERE algorithm = 'rf_xgb_lstm' AND model_version = %s""",
                (asset["asset_id"], forecast["interval"], forecast["predicted_price"], forecast["confidence"],
                 Jsonb(forecast), forecast["model_version"]),
            )
