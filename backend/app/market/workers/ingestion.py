"""Run with python -m app.market.workers.ingestion (or the Compose worker)."""
from __future__ import annotations

import asyncio
import logging
import signal

from app.core.config import Settings, get_settings
from app.market.dependencies import get_market_service
from app.market.schemas import SUPPORTED_INTERVALS
from app.market.service import MarketService

logger = logging.getLogger(__name__)


class MarketIngestionWorker:
    def __init__(self, service: MarketService, settings: Settings) -> None:
        self.service = service
        self.settings = settings

    @staticmethod
    async def pause(stop: asyncio.Event, seconds: float) -> None:
        try:
            await asyncio.wait_for(stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def ingest_history_once(self, stop: asyncio.Event) -> int:
        """Backfill a bounded window, then upsert that window on later cycles."""
        assets, _ = await asyncio.to_thread(self.service.get_top_assets, 50)
        saved = 0
        # CoinGecko can return different assets with the same exchange symbol.
        symbols = dict.fromkeys(asset.symbol for asset in assets)
        for symbol in symbols:
            for interval in SUPPORTED_INTERVALS:
                if stop.is_set():
                    return saved
                try:
                    saved += await asyncio.to_thread(
                        self.service.ingest_ohlcv, symbol, interval,
                        self.settings.market_history_candle_limit,
                    )
                except Exception:
                    # An unavailable pair/store must not prevent other assets being ingested.
                    logger.exception("History ingestion failed for %s %s; retry next cycle", symbol, interval)
                await self.pause(stop, self.settings.market_ingestion_request_spacing_seconds)
        return saved

    async def refresh_prices(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await asyncio.to_thread(self.service.get_top_assets, 50, force_refresh=True)
            except Exception:
                logger.exception("Price refresh failed; retry next cycle")
            await self.pause(stop, self.settings.market_refresh_seconds)

    async def refresh_history(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                saved = await self.ingest_history_once(stop)
                logger.info("History cycle persisted %s candle updates", saved)
            except Exception:
                logger.exception("History cycle failed; retry next cycle")
            await self.pause(stop, self.settings.market_history_refresh_seconds)

    async def run(self, stop: asyncio.Event) -> None:
        # A long history backfill must not stall the live-price refresh cadence.
        await asyncio.gather(self.refresh_prices(stop), self.refresh_history(stop))


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)
    service = get_market_service()
    await MarketIngestionWorker(service, get_settings()).run(stop)


if __name__ == "__main__":
    asyncio.run(main())
