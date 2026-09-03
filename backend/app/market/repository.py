from __future__ import annotations

from typing import Protocol

from pymongo import ASCENDING, DESCENDING, UpdateOne
from pymongo.database import Database

from app.market.schemas import MarketInterval, OhlcvCandle


class MarketRepositoryProtocol(Protocol):
    def upsert_ohlcv(self, candles: list[OhlcvCandle]) -> None: ...
    def get_ohlcv(self, symbol: str, interval: MarketInterval, limit: int) -> list[OhlcvCandle]: ...


class MongoMarketRepository:
    def __init__(self, database: Database) -> None:
        self.collection = database["market_data"]
        self.collection.create_index(
            [("symbol", ASCENDING), ("interval", ASCENDING), ("timestamp", DESCENDING)],
            unique=True,
            name="market_data_symbol_interval_timestamp",
        )

    def upsert_ohlcv(self, candles: list[OhlcvCandle]) -> None:
        if not candles:
            return
        operations = []
        for candle in candles:
            document = candle.model_dump(mode="python")
            operations.append(
                UpdateOne(
                    {
                        "symbol": candle.symbol,
                        "interval": candle.interval,
                        "timestamp": candle.timestamp,
                    },
                    {"$set": document},
                    upsert=True,
                )
            )
        self.collection.bulk_write(operations, ordered=False)

    def get_ohlcv(self, symbol: str, interval: MarketInterval, limit: int) -> list[OhlcvCandle]:
        cursor = (
            self.collection.find({"symbol": symbol.upper(), "interval": interval}, {"_id": 0})
            .sort("timestamp", DESCENDING)
            .limit(limit)
        )
        items = [OhlcvCandle.model_validate(document) for document in cursor]
        items.reverse()
        return items
