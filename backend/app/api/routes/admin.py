import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query

from app.admin.repository import AdminRepository
from app.auth.dependencies import get_admin_user
from app.core.config import get_settings

router = APIRouter(prefix='/admin', tags=['Admin'], dependencies=[Depends(get_admin_user)])


def get_repository():
    return AdminRepository(get_settings().postgres_dsn)


@router.get('/users')
def users(before: int | None = Query(None, ge=1, le=9223372036854775807),
          limit: int = Query(25, ge=1, le=100), repository=Depends(get_repository)):
    try:
        return repository.users(before,limit)
    except psycopg.Error:
        raise HTTPException(503,'Administration storage is unavailable') from None


@router.get('/overview')
def overview(repository=Depends(get_repository)):
    try:
        return repository.overview()
    except psycopg.Error:
        raise HTTPException(503,'Administration storage is unavailable') from None


@router.get('/models')
def models(before: int | None = Query(None, ge=1, le=9223372036854775807),
           limit: int = Query(25, ge=1, le=100), repository=Depends(get_repository)):
    try:
        return repository.models(before,limit)
    except psycopg.Error:
        raise HTTPException(503,'Model administration storage is unavailable') from None


@router.get('/operations')
def operations(repository=Depends(get_repository)):
    try:
        return repository.operations()
    except psycopg.Error:
        raise HTTPException(503,'Operational status storage is unavailable') from None


from typing import Literal
from pydantic import BaseModel
from fastapi import Path
from app.portfolio.risk import PortfolioError
from app.admin.health import health
from app.prediction.dependencies import get_prediction_service


class UserUpdate(BaseModel):
    role: Literal['trader','admin']
    is_active: bool


@router.put('/users/{user_id}')
def update_user(body: UserUpdate, user_id: int = Path(ge=1,le=9223372036854775807),
                actor=Depends(get_admin_user),repository=Depends(get_repository)):
    try:
        return repository.update_user(actor['user_id'],user_id,body.role,body.is_active)
    except PortfolioError as exc:
        raise HTTPException(exc.status_code,str(exc)) from None
    except psycopg.Error:
        raise HTTPException(503,'User administration storage is unavailable') from None


@router.get('/audit')
def audit(before: int | None = Query(None,ge=1,le=9223372036854775807),
          limit: int = Query(25,ge=1,le=100),repository=Depends(get_repository)):
    try:
        return repository.audit(before,limit)
    except psycopg.Error:
        raise HTTPException(503,'Audit storage is unavailable') from None


@router.post('/health/check')
def check_health():
    return health()


@router.post('/models/{model_id}/check')
def check_model(model_id: int = Path(ge=1,le=9223372036854775807),repository=Depends(get_repository),
                service=Depends(get_prediction_service)):
    from datetime import datetime,timezone
    from psycopg.rows import dict_row
    try:
        with psycopg.connect(repository.dsn,row_factory=dict_row) as c:
            model=c.execute('SELECT symbol,timeframe,is_active,model_version FROM ml_models WHERE model_id=%s',(model_id,)).fetchone()
    except psycopg.Error:
        raise HTTPException(503,'Model storage unavailable') from None
    if not model:
        raise HTTPException(404,'Model not found')
    if not model['is_active'] or not model['symbol'] or not model['timeframe']:
        raise HTTPException(409,'Only an active prediction model can be checked')
    try:
        forecast=service.predict(model['symbol'],model['timeframe'])
        state='healthy' if forecast.model_version==model['model_version'] else 'model_changed'
    except Exception:
        state='unavailable'
    return {'model_id':model_id,'status':state,'observed_at':datetime.now(timezone.utc),
            'scope':'Runs and records a forecast using the active model, including artifact and candle validation.'}
