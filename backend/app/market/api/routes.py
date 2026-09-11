from fastapi import APIRouter

from app.market.services.coingecko import CoinGeckoProvider
from app.market.services.indicators import calculate_indicators

router = APIRouter(prefix="/market", tags=["market"])
provider = CoinGeckoProvider()


@router.get("/assets")
async def assets():
    return await provider.get_assets()


@router.get("/{symbol}/price")
async def price(symbol: str):
    return await provider.get_price(symbol)


@router.get("/{symbol}/ohlcv")
async def ohlcv(symbol: str, timeframe: str = "1h"):
    return await provider.get_ohlcv(symbol, timeframe)


@router.post("/{symbol}/indicators")
async def indicators(symbol: str, candles: list[dict]):
    result = calculate_indicators(candles)
    return result.tail(1).to_dict(orient="records")
