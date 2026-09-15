from datetime import datetime
from decimal import Decimal
from uuid import UUID
import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from app.auth.dependencies import get_current_user
from app.core.config import get_settings
from app.exchange.adapters import ExchangeFailure
from app.exchange.contracts import Credentials
from app.exchange.repository import ExchangeRepository
from app.exchange.schemas import ConnectionCreate
from app.exchange.service import ExchangeService, capabilities


class SecretSafeRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request):
            try:
                return await original(request)
            except RequestValidationError as exc:
                # Default FastAPI errors echo raw inputs, which may contain credentials.
                errors = [{k: error[k] for k in ('loc', 'type', 'msg')} for error in exc.errors()]
                return JSONResponse(status_code=422, content=jsonable_encoder({'detail': errors}))
        return handler


router = APIRouter(prefix='/exchanges', tags=['Exchange connections'], route_class=SecretSafeRoute)


def get_exchange_service():
    settings = get_settings()
    return ExchangeService(ExchangeRepository(settings.postgres_dsn), settings)


def respond(operation, *args):
    try:
        return JSONResponse(jsonable_encoder(operation(*args), custom_encoder={Decimal: str}))
    except ExchangeFailure as exc:
        raise HTTPException(exc.status_code, str(exc)) from None
    except psycopg.Error:
        raise HTTPException(503, 'Exchange connection storage is unavailable') from None


@router.get('/capabilities')
def available(user=Depends(get_current_user)):
    return capabilities()


@router.get('')
def connections(user=Depends(get_current_user), service=Depends(get_exchange_service)):
    return respond(service.list, user['user_id'])


@router.post('')
def create(body: ConnectionCreate, user=Depends(get_current_user), service=Depends(get_exchange_service)):
    return respond(service.create, user['user_id'], body)


@router.put('/{connection_id}/credentials')
def replace(connection_id: UUID, body: Credentials, user=Depends(get_current_user), service=Depends(get_exchange_service)):
    return respond(service.replace_credentials, user['user_id'], connection_id, body)


@router.delete('/{connection_id}')
def delete(connection_id: UUID, user=Depends(get_current_user), service=Depends(get_exchange_service)):
    return respond(service.repository.delete, user['user_id'], connection_id)


@router.post('/{connection_id}/verify')
def verify(connection_id: UUID, user=Depends(get_current_user), service=Depends(get_exchange_service)):
    return respond(service.read, user['user_id'], connection_id, 'connect')


@router.get('/{connection_id}/balances')
def balances(connection_id: UUID, user=Depends(get_current_user), service=Depends(get_exchange_service)):
    return respond(service.read, user['user_id'], connection_id, 'get_balance')


@router.get('/{connection_id}/price')
def price(connection_id: UUID, symbol: str = Query(pattern=r'^[A-Z0-9]+/[A-Z0-9]+$', max_length=41),
          user=Depends(get_current_user), service=Depends(get_exchange_service)):
    return respond(service.read, user['user_id'], connection_id, 'get_price', symbol)


@router.get('/{connection_id}/orders/{order_id}')
def order(connection_id: UUID, order_id: str, symbol: str = Query(pattern=r'^[A-Z0-9]+/[A-Z0-9]+$', max_length=41),
          user=Depends(get_current_user), service=Depends(get_exchange_service)):
    if len(order_id) > 200:
        raise HTTPException(422, 'Invalid order ID')
    return respond(service.read, user['user_id'], connection_id, 'get_order', order_id, symbol)


@router.get('/{connection_id}/trades')
def trades(connection_id: UUID, symbol: str = Query(pattern=r'^[A-Z0-9]+/[A-Z0-9]+$', max_length=41),
           since: datetime | None = None, limit: int = Query(50, ge=1, le=100),
           user=Depends(get_current_user), service=Depends(get_exchange_service)):
    if since is not None and since.tzinfo is None:
        raise HTTPException(422, 'Trade start time must include a timezone')
    def fetch():
        items = service.read(user['user_id'], connection_id, 'get_trades', symbol, since, limit)
        return {'items': items, 'limit': limit, 'since': since, 'possibly_truncated': len(items) >= limit}
    return respond(fetch)
