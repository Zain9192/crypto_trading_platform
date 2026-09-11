from decimal import Decimal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.auth.dependencies import get_current_user
from app.core.config import get_settings
from app.market.dependencies import get_market_service
from app.portfolio.repository import PostgresPortfolioRepository
from app.portfolio.risk import PortfolioError
from app.portfolio.schemas import PaperOrderCreate, PortfolioCreate, RiskSettings
from app.portfolio.service import PortfolioService

router = APIRouter(prefix="/portfolios", tags=["Portfolio and risk"])


def get_portfolio_service():
    return PortfolioService(PostgresPortfolioRepository(get_settings().postgres_dsn), get_market_service())


def respond(operation, *args):
    try:
        # Money remains decimal strings on the wire, never binary floating point.
        return JSONResponse(jsonable_encoder(operation(*args), custom_encoder={Decimal: str}))
    except PortfolioError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(503, "Portfolio storage is unavailable") from exc


@router.get("")
def list_portfolios(user=Depends(get_current_user), service=Depends(get_portfolio_service)):
    return respond(service.list, user["user_id"])


@router.post("")
def create_portfolio(body: PortfolioCreate, user=Depends(get_current_user), service=Depends(get_portfolio_service)):
    return respond(service.create, user["user_id"], body)


@router.get("/{portfolio_id}")
def overview(portfolio_id: int, user=Depends(get_current_user), service=Depends(get_portfolio_service)):
    return respond(service.overview, user["user_id"], portfolio_id)


@router.put("/{portfolio_id}/risk")
def update_risk(portfolio_id: int, body: RiskSettings, user=Depends(get_current_user), service=Depends(get_portfolio_service)):
    return respond(service.settings, user["user_id"], portfolio_id, body)


@router.post("/{portfolio_id}/orders/preview")
def preview_order(portfolio_id: int, body: PaperOrderCreate, user=Depends(get_current_user), service=Depends(get_portfolio_service)):
    return respond(service.preview, user["user_id"], portfolio_id, body)


@router.post("/{portfolio_id}/orders")
def reserve_order(portfolio_id: int, body: PaperOrderCreate, user=Depends(get_current_user), service=Depends(get_portfolio_service)):
    return respond(service.reserve, user["user_id"], portfolio_id, body)


@router.post("/{portfolio_id}/orders/{order_id}/fill")
def fill_order(portfolio_id: int, order_id: UUID, user=Depends(get_current_user), service=Depends(get_portfolio_service)):
    return respond(service.complete, user["user_id"], portfolio_id, order_id, "fill")


@router.post("/{portfolio_id}/orders/{order_id}/cancel")
def cancel_order(portfolio_id: int, order_id: UUID, user=Depends(get_current_user), service=Depends(get_portfolio_service)):
    return respond(service.complete, user["user_id"], portfolio_id, order_id, "cancel")


@router.get("/{portfolio_id}/trades")
def trade_history(portfolio_id: int, limit: int = Query(25, ge=1, le=100), before: int | None = Query(None, ge=1),
                  user=Depends(get_current_user), service=Depends(get_portfolio_service)):
    return respond(service.history, user["user_id"], portfolio_id, limit, before)
