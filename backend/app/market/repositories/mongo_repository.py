class MarketRepository:
    def __init__(self, database):
        self.collection = database["ohlcv"]

    async def save_candle(self, candle: dict):
        await self.collection.update_one(
            {
                "symbol": candle["symbol"],
                "timestamp": candle["timestamp"],
            },
            {"$set": candle},
            upsert=True,
        )

    async def get_candles(self, symbol: str, limit: int = 100):
        cursor = (
            self.collection.find({"symbol": symbol})
            .sort("timestamp", -1)
            .limit(limit)
        )
        return await cursor.to_list(length=limit)
