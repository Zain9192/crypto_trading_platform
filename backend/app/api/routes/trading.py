from decimal import Decimal
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.auth.dependencies import get_current_user
from app.core.config import get_settings
from app.market.dependencies import get_market_service
from app.trading.contracts import BotConfig
from app.trading.engine import TradingEngine
from app.trading.repository import TradingRepository
from app.trading.service import TradingService
from app.portfolio.risk import PortfolioError

router = APIRouter(prefix='/bots', tags=['Paper trading bots'])


def get_service():
    return TradingService(TradingRepository(get_settings().postgres_dsn))


def respond(operation, *args):
    try:
        return JSONResponse(jsonable_encoder(operation(*args), custom_encoder={Decimal: str}))
    except PortfolioError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None
    except psycopg.Error:
        raise HTTPException(503, 'Trading storage is unavailable; verify migrations and database access') from None


@router.get('')
def listing(user=Depends(get_current_user), service=Depends(get_service)):
    return respond(service.repository.list, user['user_id'])


@router.post('')
def create(body: BotConfig, user=Depends(get_current_user), service=Depends(get_service)):
    return respond(service.repository.create, user['user_id'], body)


@router.get('/{bot_id}')
def get(bot_id: UUID, user=Depends(get_current_user), service=Depends(get_service)):
    return respond(service.repository.get, user['user_id'], bot_id)


@router.put('/{bot_id}')
def update(bot_id: UUID, body: BotConfig, user=Depends(get_current_user), service=Depends(get_service)):
    return respond(service.update, user['user_id'], bot_id, body)


@router.post('/{bot_id}/control/{action}')
def control(bot_id: UUID, action: Literal['start', 'stop', 'reset'], user=Depends(get_current_user), service=Depends(get_service)):
    return respond(service.control, user['user_id'], bot_id, action)


@router.get('/{bot_id}/history')
def history(bot_id: UUID, before: int | None = Query(None, ge=1), limit: int = Query(25, ge=1, le=100),
            user=Depends(get_current_user), service=Depends(get_service)):
    return respond(service.repository.history, user['user_id'], bot_id, before, limit)


@router.post('/{bot_id}/close-position')
def close_position(bot_id: UUID, user=Depends(get_current_user), service=Depends(get_service), market=Depends(get_market_service)):
    def close():
        row = service.repository.get(user['user_id'], bot_id)
        if row['connection_id'] is not None:
            return service.sandbox_action(user['user_id'], bot_id, 'close')
        try:
            asset = market.get_asset(row['symbol'].split('/')[0])
        except Exception:
            raise PortfolioError('Market quote unavailable', 503) from None
        if asset is None:
            raise PortfolioError('Market quote unavailable', 503)
        return TradingEngine(service.repository).tick(user['user_id'], bot_id, row['revision'], asset, close=True)
    return respond(close)


@router.post('/{bot_id}/sandbox/{action}')
def sandbox_control(bot_id: UUID, action: Literal['close', 'cancel', 'reconcile'], order_id: UUID | None = None,
                    user=Depends(get_current_user), service=Depends(get_service)):
    return respond(service.sandbox_action, user['user_id'], bot_id, action, order_id)
