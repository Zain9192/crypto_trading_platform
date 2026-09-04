import httpx

from .provider import MarketProvider


class CoinGeckoProvider(MarketProvider):
    BASE_URL = "https://api.coingecko.com/api/v3"

    async def get_assets(self):
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/coins/markets",
                params={
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": 50,
                    "page": 1,
                },
            )
            response.raise_for_status()
            return response.json()

    async def get_price(self, symbol: str):
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/simple/price",
                params={"ids": symbol, "vs_currencies": "usd"},
            )
            response.raise_for_status()
            return response.json()

    async def get_ohlcv(self, symbol: str, timeframe: str = "1h"):
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/coins/{symbol}/ohlc",
                params={"vs_currency": "usd", "days": 30},
            )
            response.raise_for_status()
            return response.json()
