from datetime import date
from decimal import Decimal
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, WebSocket
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.core.config import get_settings
from app.market.dependencies import get_market_service
from app.notifications.alerts import PriceAlertInput, PriceAlerts
from app.notifications.email_worker import configured
from app.notifications.reports import export_report
from app.notifications.repository import NotificationRepository
from app.notifications.socket import notification_socket

router = APIRouter(prefix='/notifications', tags=['Notifications'])


def get_repository():
    return NotificationRepository(get_settings().postgres_dsn)


@router.get('')
def listing(before: int | None = Query(None, ge=1), limit: int = Query(25, ge=1, le=100),
            unread_only: bool = False, user=Depends(get_current_user), repository=Depends(get_repository)):
    try:
        return repository.listing(user['user_id'], before, limit, unread_only)
    except psycopg.Error:
        raise HTTPException(503, 'Notification storage is unavailable') from None


@router.post('/{notification_id}/read')
def mark_read(notification_id: int = Path(ge=1), user=Depends(get_current_user),
              repository=Depends(get_repository)):
    try:
        row = repository.mark_read(user['user_id'], notification_id)
    except psycopg.Error:
        raise HTTPException(503, 'Notification storage is unavailable') from None
    if row is None:
        raise HTTPException(404, 'Notification not found')
    return row




def get_alerts():
    return PriceAlerts(get_settings().postgres_dsn)


@router.get('/price-alerts')
def list_alerts(user=Depends(get_current_user), alerts=Depends(get_alerts)):
    try:
        return jsonable_encoder(alerts.listing(user['user_id']), custom_encoder={Decimal: str})
    except psycopg.Error:
        raise HTTPException(503, 'Alert storage is unavailable') from None


@router.post('/price-alerts', status_code=201)
def create_alert(body: PriceAlertInput, user=Depends(get_current_user), alerts=Depends(get_alerts),
                 market=Depends(get_market_service)):
    try:
        assets, _ = market.get_top_assets(50)
    except Exception:
        raise HTTPException(503, 'Market assets are unavailable') from None
    if not any(asset.id == body.asset_key for asset in assets):
        raise HTTPException(422, 'Choose an asset from the current top-50 market list')
    try:
        return jsonable_encoder(alerts.create(user['user_id'], body), custom_encoder={Decimal: str})
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    except psycopg.Error:
        raise HTTPException(503, 'Alert storage is unavailable') from None


@router.delete('/price-alerts/{alert_id}')
def delete_alert(alert_id: int = Path(ge=1), user=Depends(get_current_user), alerts=Depends(get_alerts)):
    try:
        deleted = alerts.delete(user['user_id'], alert_id)
    except psycopg.Error:
        raise HTTPException(503, 'Alert storage is unavailable') from None
    if not deleted:
        raise HTTPException(404, 'Price alert not found')
    return {'deleted': True}


@router.websocket('/ws')
async def live_notifications(socket: WebSocket):
    await notification_socket(socket)




class EmailPreference(BaseModel):
    email_enabled: bool


@router.get('/preferences')
def preferences(user=Depends(get_current_user), repository=Depends(get_repository)):
    try:
        return {**repository.preferences(user['user_id']),
                'delivery_configured': configured(get_settings())}
    except psycopg.Error:
        raise HTTPException(503, 'Notification storage is unavailable') from None


@router.put('/preferences')
def set_preferences(body: EmailPreference, user=Depends(get_current_user), repository=Depends(get_repository)):
    if body.email_enabled and not user['is_email_verified']:
        raise HTTPException(409, 'Verify your email before enabling notifications')
    try:
        return repository.preferences(user['user_id'], body.email_enabled)
    except psycopg.Error:
        raise HTTPException(503, 'Notification storage is unavailable') from None


@router.get('/reports/trades')
def report(start: date, end: date, format: Literal['csv', 'pdf'], user=Depends(get_current_user)):
    try:
        return export_report(get_settings().postgres_dsn, user['user_id'], start, end, format)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from None
    except psycopg.Error:
        raise HTTPException(503,'Report storage is unavailable') from None
