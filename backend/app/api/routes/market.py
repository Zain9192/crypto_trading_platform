from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from app.core.config import get_settings
from app.market.dependencies import get_market_service
from app.market.providers import ProviderError
from app.market.schemas import (
    IndicatorResponse,
    MarketAsset,
    MarketAssetsResponse,
    MarketInterval,
    MarketStreamMessage,
    OhlcvResponse,
)
from app.market.service import MarketService

router = APIRouter(prefix="/market", tags=["market-data"])


@router.get("/assets", response_model=MarketAssetsResponse)
def list_assets(
    service: Annotated[MarketService, Depends(get_market_service)],
    limit: int = Query(default=50, ge=1, le=50),
) -> MarketAssetsResponse:
    try:
        assets, cached = service.get_top_assets(limit)
    except ProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    settings = get_settings()
    return MarketAssetsResponse(
        items=assets,
        count=len(assets),
        cached=cached,
        refresh_seconds=settings.market_refresh_seconds,
    )


@router.get("/assets/{symbol}", response_model=MarketAsset)
def get_asset(symbol: str, service: Annotated[MarketService, Depends(get_market_service)]) -> MarketAsset:
    try:
        asset = service.get_asset(symbol)
    except (ProviderError, ValueError) as exc:
        status_code = status.HTTP_502_BAD_GATEWAY if isinstance(exc, ProviderError) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found in the top-50 market set")
    return asset


@router.get("/ohlcv/{symbol}", response_model=OhlcvResponse)
def get_ohlcv(
    symbol: str,
    service: Annotated[MarketService, Depends(get_market_service)],
    interval: MarketInterval = Query(default="1d"),
    limit: int = Query(default=200, ge=20, le=1000),
) -> OhlcvResponse:
    try:
        candles, cached = service.get_ohlcv(symbol, interval, limit)
    except ProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return OhlcvResponse(
        symbol=symbol.upper(),
        interval=interval,
        items=candles,
        count=len(candles),
        cached=cached,
    )


@router.get("/indicators/{symbol}", response_model=IndicatorResponse)
def get_indicators(
    symbol: str,
    service: Annotated[MarketService, Depends(get_market_service)],
    interval: MarketInterval = Query(default="1d"),
    limit: int = Query(default=200, ge=20, le=1000),
) -> IndicatorResponse:
    try:
        points = service.get_indicators(symbol, interval, limit)
    except ProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return IndicatorResponse(symbol=symbol.upper(), interval=interval, items=points, count=len(points))


@router.websocket("/ws/prices")
async def stream_prices(
    websocket: WebSocket,
    service: Annotated[MarketService, Depends(get_market_service)],
) -> None:
    await websocket.accept()
    settings = get_settings()
    try:
        requested_limit = int(websocket.query_params.get("limit", "50"))
    except ValueError:
        requested_limit = 50
    limit = max(1, min(requested_limit, 50))

    try:
        while True:
            try:
                assets, _ = await asyncio.to_thread(service.get_top_assets, limit)
                message = MarketStreamMessage(
                    generated_at=datetime.now(timezone.utc),
                    refresh_seconds=settings.market_refresh_seconds,
                    items=assets,
                )
                await websocket.send_json(message.model_dump(mode="json"))
            except ProviderError as exc:
                await websocket.send_json({"type": "error", "detail": str(exc)})
            await asyncio.sleep(settings.market_refresh_seconds)
    except WebSocketDisconnect:
        return
