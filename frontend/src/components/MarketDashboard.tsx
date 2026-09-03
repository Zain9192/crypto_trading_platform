import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useState } from 'react'

import {
  fetchIndicators,
  fetchOhlcv,
  fetchTopAssets,
  type MarketAsset,
  type MarketAssetsResponse,
  type MarketInterval,
} from '../api/market'
import { useMarketSocket } from '../hooks/useMarketSocket'
import CandlestickChart from './CandlestickChart'

const intervals: MarketInterval[] = ['1h', '4h', '1d', '1w', '1M']

function compactCurrency(value?: number | null): string {
  if (value === null || value === undefined) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    notation: Math.abs(value) >= 1_000_000 ? 'compact' : 'standard',
    maximumFractionDigits: value < 1 ? 6 : 2,
  }).format(value)
}

function compactNumber(value?: number | null): string {
  if (value === null || value === undefined) return '—'
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(value)
}

function indicatorValue(value?: number | null, digits = 2): string {
  return value === null || value === undefined ? '—' : value.toFixed(digits)
}

export default function MarketDashboard() {
  const queryClient = useQueryClient()
  const [selectedSymbol, setSelectedSymbol] = useState('BTC')
  const [interval, setInterval] = useState<MarketInterval>('1d')

  const assetsQuery = useQuery({
    queryKey: ['market-assets'],
    queryFn: () => fetchTopAssets(50),
    staleTime: 25_000,
    refetchInterval: 30_000,
    retry: 1,
  })

  const updateFromSocket = useCallback(
    (items: MarketAsset[]) => {
      queryClient.setQueryData<MarketAssetsResponse>(['market-assets'], (existing) => ({
        items,
        count: items.length,
        cached: true,
        refresh_seconds: existing?.refresh_seconds ?? 30,
        source: existing?.source ?? 'coingecko',
      }))
    },
    [queryClient],
  )
  useMarketSocket(updateFromSocket)

  const ohlcvQuery = useQuery({
    queryKey: ['ohlcv', selectedSymbol, interval],
    queryFn: () => fetchOhlcv(selectedSymbol, interval, 200),
    staleTime: 60_000,
    retry: 1,
  })

  const indicatorsQuery = useQuery({
    queryKey: ['indicators', selectedSymbol, interval],
    queryFn: () => fetchIndicators(selectedSymbol, interval, 200),
    staleTime: 60_000,
    retry: 1,
  })

  const selectedAsset = useMemo(
    () => assetsQuery.data?.items.find((asset) => asset.symbol === selectedSymbol),
    [assetsQuery.data, selectedSymbol],
  )
  const latestIndicators = indicatorsQuery.data?.items.at(-1)

  return (
    <div className="market-layout">
      <section className="market-panel market-overview">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Live market feed</p>
            <h2>Top 50 cryptocurrencies</h2>
          </div>
          <span className="live-pill"><span className="status-dot" />30s refresh</span>
        </div>
        {assetsQuery.isError && <p className="error-banner">{assetsQuery.error.message}</p>}
        <div className="market-table-wrap">
          <table className="market-table">
            <thead>
              <tr><th>#</th><th>Asset</th><th>Price</th><th>24h</th><th>Market cap</th><th>Volume</th></tr>
            </thead>
            <tbody>
              {assetsQuery.data?.items.map((asset) => (
                <tr
                  key={asset.id}
                  className={asset.symbol === selectedSymbol ? 'selected-row' : undefined}
                  onClick={() => setSelectedSymbol(asset.symbol)}
                >
                  <td>{asset.market_cap_rank ?? '—'}</td>
                  <td>
                    <div className="asset-cell">
                      {asset.image && <img src={asset.image} alt="" />}
                      <span><strong>{asset.symbol}</strong><small>{asset.name}</small></span>
                    </div>
                  </td>
                  <td>{compactCurrency(asset.current_price)}</td>
                  <td className={(asset.price_change_percentage_24h ?? 0) >= 0 ? 'positive' : 'negative'}>
                    {asset.price_change_percentage_24h === null || asset.price_change_percentage_24h === undefined
                      ? '—'
                      : `${asset.price_change_percentage_24h.toFixed(2)}%`}
                  </td>
                  <td>{compactCurrency(asset.market_cap)}</td>
                  <td>{compactCurrency(asset.total_volume)}</td>
                </tr>
              ))}
              {assetsQuery.isLoading && (
                <tr><td colSpan={6} className="table-state">Loading market data…</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="market-panel chart-panel">
        <div className="section-heading chart-heading">
          <div>
            <p className="eyebrow">{selectedAsset?.name ?? selectedSymbol}</p>
            <h2>{selectedSymbol} / USDT</h2>
            <p className="price-line">{compactCurrency(selectedAsset?.current_price)}</p>
          </div>
          <div className="interval-tabs" aria-label="Chart interval">
            {intervals.map((value) => (
              <button key={value} type="button" className={value === interval ? 'active' : ''} onClick={() => setInterval(value)}>
                {value.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
        {ohlcvQuery.isError && <p className="error-banner">{ohlcvQuery.error.message}</p>}
        {ohlcvQuery.data?.items.length ? (
          <CandlestickChart candles={ohlcvQuery.data.items} />
        ) : (
          <div className="chart-placeholder">{ohlcvQuery.isLoading ? 'Loading candles…' : 'No candle data available.'}</div>
        )}

        <div className="indicator-grid">
          <div><span>RSI 14</span><strong>{indicatorValue(latestIndicators?.rsi_14)}</strong></div>
          <div><span>SMA 20</span><strong>{indicatorValue(latestIndicators?.sma_20, 4)}</strong></div>
          <div><span>EMA 20</span><strong>{indicatorValue(latestIndicators?.ema_20, 4)}</strong></div>
          <div><span>MACD</span><strong>{indicatorValue(latestIndicators?.macd, 4)}</strong></div>
          <div><span>MACD signal</span><strong>{indicatorValue(latestIndicators?.macd_signal, 4)}</strong></div>
          <div><span>Volume</span><strong>{compactNumber(latestIndicators?.volume)}</strong></div>
          <div><span>BB upper</span><strong>{indicatorValue(latestIndicators?.bb_upper, 4)}</strong></div>
          <div><span>BB lower</span><strong>{indicatorValue(latestIndicators?.bb_lower, 4)}</strong></div>
        </div>
      </section>
    </div>
  )
}
