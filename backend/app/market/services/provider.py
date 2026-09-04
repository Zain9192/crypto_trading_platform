from abc import ABC, abstractmethod


class MarketProvider(ABC):

    @abstractmethod
    async def get_assets(self):
        pass

    @abstractmethod
    async def get_price(self, symbol: str):
        pass

    @abstractmethod
    async def get_ohlcv(self, symbol: str, timeframe: str):
        pass
