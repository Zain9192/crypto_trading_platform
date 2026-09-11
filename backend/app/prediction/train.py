"""Operator-only offline training: python -m app.prediction.train --help."""
from __future__ import annotations

import argparse
import json

from app.core.config import get_settings
from app.market.dependencies import get_market_service
from app.market.schemas import SUPPORTED_INTERVALS
from app.prediction.artifacts import ArtifactStore
from app.prediction.registry import PostgresRegistry
from app.prediction.training import train_version


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a versioned RF/XGBoost/LSTM bundle on closed MongoDB candles")
    parser.add_argument("--symbol")
    parser.add_argument("--activate-version", help="Verify and activate an existing immutable candidate version")
    parser.add_argument("--interval", choices=SUPPORTED_INTERVALS, default="1d")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--lookback", type=int, default=20)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--trees", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fee-bps", type=float, default=10)
    parser.add_argument("--activate", action="store_true", help="Explicitly make the evaluated bundle available for inference")
    args = parser.parse_args()
    settings = get_settings()
    if args.activate_version:
        registry = PostgresRegistry(settings.postgres_dsn)
        record = registry.version(args.activate_version)
        if record is None:
            parser.error("Unknown model version")
        ArtifactStore(settings.prediction_artifact_dir).load(record["version"], record["checksum"])
        registry.activate(record["version"])
        print(json.dumps({"version": record["version"], "active": True}))
        return
    if not args.symbol:
        parser.error("--symbol is required for training")
    if not 300 <= args.limit <= 1000:
        parser.error("--limit must be between 300 and 1000")
    settings = get_settings()
    candles = get_market_service().get_history(args.symbol.upper(), args.interval, args.limit)
    record = train_version(candles, ArtifactStore(settings.prediction_artifact_dir),
                           PostgresRegistry(settings.postgres_dsn), lookback=args.lookback,
                           epochs=args.epochs, trees=args.trees, seed=args.seed,
                           fee_bps=args.fee_bps, activate=args.activate)
    print(json.dumps({"version": record["version"], "active": args.activate,
                      "metrics": record["metadata"]["metrics"],
                      "backtest": record["metadata"]["backtest"]}, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
