import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from pymongo.errors import PyMongoError

from app.core.config import Settings
from app.market.providers import ProviderError
from app.market.schemas import MarketAsset, SUPPORTED_INTERVALS
from app.market.service import MarketService
from app.market.workers.ingestion import MarketIngestionWorker


def worker(service):
    return MarketIngestionWorker(service, Settings(market_ingestion_request_spacing_seconds=0.01))


def test_history_cycle_ingests_all_intervals_and_continues_after_provider_failure():
    service = Mock()
    service.get_top_assets.return_value = ([
        MarketAsset(id="bitcoin", symbol="BTC", name="Bitcoin"),
        MarketAsset(id="ethereum", symbol="ETH", name="Ethereum"),
    ], True)
    service.ingest_ohlcv.side_effect = [ProviderError("Pair unavailable")] + [20] * 9
    saved = asyncio.run(worker(service).ingest_history_once(asyncio.Event()))
    assert saved == 180
    assert service.ingest_ohlcv.call_count == 10
    assert {(call.args[0], call.args[1]) for call in service.ingest_ohlcv.call_args_list} == {
        (symbol, interval) for symbol in ("BTC", "ETH") for interval in SUPPORTED_INTERVALS
    }


def test_stop_prevents_new_provider_requests():
    service = Mock()
    service.get_top_assets.return_value = ([MarketAsset(id="btc", symbol="BTC", name="Bitcoin")], True)

    async def run():
        stop = asyncio.Event()
        stop.set()
        return await worker(service).ingest_history_once(stop)

    assert asyncio.run(run()) == 0
    service.ingest_ohlcv.assert_not_called()


def test_price_loop_retries_and_stops_during_wait():
    async def run():
        service = Mock()
        stop = asyncio.Event()
        calls = 0

        loop = asyncio.get_running_loop()
        def refresh_then_stop(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ProviderError("Temporary outage")
            loop.call_soon_threadsafe(stop.set)

        service.get_top_assets.side_effect = refresh_then_stop
        instance = worker(service)
        instance.pause = AsyncMock()
        await asyncio.wait_for(instance.refresh_prices(stop), 1)
        assert calls == 2
        service.get_top_assets.assert_called_with(50, force_refresh=True)

    asyncio.run(run())


def test_ingestion_does_not_report_success_when_persistence_fails():
    provider, repository, cache = Mock(), Mock(), Mock()
    provider.fetch_ohlcv.return_value = []
    repository.upsert_ohlcv.side_effect = PyMongoError("Database unavailable")
    service = MarketService(Mock(), provider, repository, cache)
    with pytest.raises(PyMongoError):
        service.ingest_ohlcv("btc", "1w", 20)
    cache.set_ohlcv.assert_not_called()


def test_saved_history_does_not_call_exchange_or_cache():
    provider, repository, cache = Mock(), Mock(), Mock()
    repository.get_ohlcv.return_value = []
    service = MarketService(Mock(), provider, repository, cache)
    assert service.get_history(" btc ", "1M", 20) == []
    repository.get_ohlcv.assert_called_once_with("BTC", "1M", 20)
    provider.fetch_ohlcv.assert_not_called()
    cache.get_ohlcv.assert_not_called()
