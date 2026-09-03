from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

import httpx

from app.market.schemas import MarketAsset, MarketInterval, OhlcvCandle, SUPPORTED_INTERVALS


class ProviderError(RuntimeError):
    """Raised when a public market-data provider cannot satisfy a request."""


class MarketSnapshotProvider(Protocol):
    def fetch_top_assets(self, limit: int) -> list[MarketAsset]: ...


class OhlcvProvider(Protocol):
    def fetch_ohlcv(self, symbol: str, interval: MarketInterval, limit: int) -> list[OhlcvCandle]: ...


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


class CoinGeckoMarketProvider:
    def __init__(self, base_url: str, timeout_seconds: float = 10.0, client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout_seconds, headers={"Accept": "application/json"})

    def fetch_top_assets(self, limit: int) -> list[MarketAsset]:
        if limit < 1 or limit > 50:
            raise ValueError("Top asset limit must be between 1 and 50")

        try:
            response = self._client.get(
                f"{self.base_url}/coins/markets",
                params={
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": limit,
                    "page": 1,
                    "sparkline": "false",
                    "price_change_percentage": "24h",
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError("CoinGecko market request failed") from exc

        if not isinstance(payload, list):
            raise ProviderError("CoinGecko returned an unexpected response")

        assets: list[MarketAsset] = []
        for item in payload:
            assets.append(
                MarketAsset(
                    id=str(item.get("id", "")),
                    symbol=str(item.get("symbol", "")).upper(),
                    name=str(item.get("name", "")),
                    image=item.get("image"),
                    current_price=item.get("current_price"),
                    market_cap=item.get("market_cap"),
                    market_cap_rank=item.get("market_cap_rank"),
                    total_volume=item.get("total_volume"),
                    high_24h=item.get("high_24h"),
                    low_24h=item.get("low_24h"),
                    price_change_percentage_24h=item.get("price_change_percentage_24h"),
                    circulating_supply=item.get("circulating_supply"),
                    last_updated=_parse_datetime(item.get("last_updated")),
                )
            )
        return assets


class BinanceOhlcvProvider:
    def __init__(
        self,
        base_url: str,
        quote_asset: str = "USDT",
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.quote_asset = quote_asset.upper()
        self._client = client or httpx.Client(timeout=timeout_seconds, headers={"Accept": "application/json"})

    def fetch_ohlcv(self, symbol: str, interval: MarketInterval, limit: int) -> list[OhlcvCandle]:
        if interval not in SUPPORTED_INTERVALS:
            raise ValueError(f"Unsupported interval: {interval}")
        if limit < 1 or limit > 1000:
            raise ValueError("OHLCV limit must be between 1 and 1000")

        base_symbol = symbol.upper().strip()
        if not base_symbol:
            raise ValueError("Symbol is required")
        pair = base_symbol if base_symbol.endswith(self.quote_asset) else f"{base_symbol}{self.quote_asset}"

        try:
            response = self._client.get(
                f"{self.base_url}/api/v3/klines",
                params={"symbol": pair, "interval": interval, "limit": limit},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"Binance OHLCV request failed for {base_symbol}") from exc

        if not isinstance(payload, list):
            raise ProviderError("Binance returned an unexpected OHLCV response")

        candles: list[OhlcvCandle] = []
        for row in payload:
            if not isinstance(row, list) or len(row) < 6:
                raise ProviderError("Binance returned malformed OHLCV data")
            candles.append(
                OhlcvCandle(
                    symbol=base_symbol.removesuffix(self.quote_asset),
                    interval=interval,
                    timestamp=datetime.fromtimestamp(float(row[0]) / 1000, tz=timezone.utc),
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                    quote_asset=self.quote_asset,
                    provider="binance",
                )
            )
        return candles
