from __future__ import annotations

import json

import httpx

from app.market.providers import BinanceOhlcvProvider, CoinGeckoMarketProvider


def test_coingecko_provider_normalizes_top_assets() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["per_page"] == "2"
        payload = [
            {
                "id": "bitcoin",
                "symbol": "btc",
                "name": "Bitcoin",
                "image": "https://example.com/btc.png",
                "current_price": 65000,
                "market_cap": 1000000,
                "market_cap_rank": 1,
                "total_volume": 50000,
                "high_24h": 66000,
                "low_24h": 64000,
                "price_change_percentage_24h": 1.2,
                "circulating_supply": 19000000,
                "last_updated": "2026-09-03T18:00:00.000Z",
            }
        ]
        return httpx.Response(200, content=json.dumps(payload).encode(), headers={"content-type": "application/json"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = CoinGeckoMarketProvider("https://example.test/api/v3", client=client)

    assets = provider.fetch_top_assets(2)

    assert len(assets) == 1
    assert assets[0].symbol == "BTC"
    assert assets[0].current_price == 65000
    assert assets[0].market_cap_rank == 1


def test_binance_provider_normalizes_ohlcv() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["symbol"] == "BTCUSDT"
        assert request.url.params["interval"] == "1h"
        payload = [[1725386400000, "60000", "61000", "59000", "60500", "125.5", 1725389999999]]
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = BinanceOhlcvProvider("https://example.test", client=client)

    candles = provider.fetch_ohlcv("btc", "1h", 100)

    assert len(candles) == 1
    assert candles[0].symbol == "BTC"
    assert candles[0].close == 60500
    assert candles[0].volume == 125.5
