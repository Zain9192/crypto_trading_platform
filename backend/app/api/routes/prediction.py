from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.errors import PyMongoError

from app.auth.dependencies import get_current_user
from app.market.schemas import MarketInterval
from app.prediction.data import DataError
from app.prediction.dependencies import get_prediction_service
from app.prediction.schemas import Forecast, RankingRequest, RankingResponse
from app.prediction.service import ModelUnavailable, PredictionService

router = APIRouter(prefix="/predictions", tags=["predictions"], dependencies=[Depends(get_current_user)])
Service = Annotated[PredictionService, Depends(get_prediction_service)]


def call_service(action):
    try:
        return action()
    except DataError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    except ModelUnavailable as exc:
        raise HTTPException(503, detail=str(exc)) from exc
    except (psycopg.Error, PyMongoError) as exc:
        raise HTTPException(503, detail="Prediction storage unavailable") from exc


@router.get("/models/{symbol}")
def models(symbol: str, service: Service, interval: MarketInterval = Query(default="1d")):
    return call_service(lambda: service.registry.list_models(symbol.upper(), interval))


@router.post("/opportunities", response_model=RankingResponse)
def opportunities(request: RankingRequest, service: Service):
    return call_service(lambda: service.rank(request.symbols, request.interval))


@router.get("/{symbol}", response_model=Forecast)
def predict(symbol: str, service: Service, interval: MarketInterval = Query(default="1d")):
    return call_service(lambda: service.predict(symbol, interval))
