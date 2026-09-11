from fastapi import Depends

from app.core.config import get_settings
from app.market.dependencies import get_market_service
from app.prediction.artifacts import ArtifactStore
from app.prediction.registry import PostgresRegistry
from app.prediction.service import PredictionService


def get_prediction_service(market=Depends(get_market_service)) -> PredictionService:
    settings = get_settings()
    return PredictionService(market, PostgresRegistry(settings.postgres_dsn),
                             ArtifactStore(settings.prediction_artifact_dir))
