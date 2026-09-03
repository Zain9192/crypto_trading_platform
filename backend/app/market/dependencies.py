from functools import lru_cache

from app.core.config import get_settings
from app.db.mongo import get_mongo_database
from app.db.redis_store import get_redis_client
from app.market.cache import RedisMarketCache
from app.market.providers import BinanceOhlcvProvider, CoinGeckoMarketProvider
from app.market.repository import MongoMarketRepository
from app.market.service import MarketService


@lru_cache
def get_market_service() -> MarketService:
    settings = get_settings()
    market_provider = CoinGeckoMarketProvider(
        base_url=settings.coingecko_base_url,
        timeout_seconds=settings.market_http_timeout_seconds,
    )
    ohlcv_provider = BinanceOhlcvProvider(
        base_url=settings.binance_market_base_url,
        quote_asset=settings.market_default_quote_asset,
        timeout_seconds=settings.market_http_timeout_seconds,
    )
    repository = MongoMarketRepository(get_mongo_database())
    cache = RedisMarketCache(get_redis_client())
    return MarketService(
        market_provider=market_provider,
        ohlcv_provider=ohlcv_provider,
        repository=repository,
        cache=cache,
        market_cache_ttl_seconds=settings.market_cache_ttl_seconds,
        ohlcv_cache_ttl_seconds=settings.ohlcv_cache_ttl_seconds,
    )
