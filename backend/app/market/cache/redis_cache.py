import json


class MarketCache:
    def __init__(self, redis_client):
        self.redis = redis_client

    async def set_price(self, symbol: str, data: dict):
        await self.redis.set(
            f"market:price:{symbol}",
            json.dumps(data),
            ex=60,
        )

    async def get_price(self, symbol: str):
        value = await self.redis.get(f"market:price:{symbol}")
        return json.loads(value) if value else None
