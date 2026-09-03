export type MarketInterval = '1h' | '4h' | '1d' | '1w' | '1M'

export interface MarketAsset {
  id: string
  symbol: string
  name: string
  image?: string | null
  current_price?: number | null
  market_cap?: number | null
  market_cap_rank?: number | null
  total_volume?: number | null
  high_24h?: number | null
  low_24h?: number | null
  price_change_percentage_24h?: number | null
  circulating_supply?: number | null
  last_updated?: string | null
}

export interface MarketAssetsResponse {
  items: MarketAsset[]
  count: number
  cached: boolean
  refresh_seconds: number
  source: string
}

export interface OhlcvCandle {
  symbol: string
  interval: MarketInterval
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  quote_asset: string
  provider: string
}

export interface OhlcvResponse {
  symbol: string
  interval: MarketInterval
  items: OhlcvCandle[]
  count: number
  cached: boolean
  source: string
}

export interface IndicatorPoint {
  timestamp: string
  close: number
  volume: number
  sma_20?: number | null
  ema_20?: number | null
  rsi_14?: number | null
  macd?: number | null
  macd_signal?: number | null
  macd_histogram?: number | null
  bb_middle?: number | null
  bb_upper?: number | null
  bb_lower?: number | null
}

export interface IndicatorResponse {
  symbol: string
  interval: MarketInterval
  items: IndicatorPoint[]
  count: number
  source: string
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

async function requestJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { headers: { Accept: 'application/json' } })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail ?? `Request failed with status ${response.status}`)
  }
  return response.json() as Promise<T>
}

export function fetchTopAssets(limit = 50): Promise<MarketAssetsResponse> {
  return requestJson<MarketAssetsResponse>(`/market/assets?limit=${limit}`)
}

export function fetchOhlcv(symbol: string, interval: MarketInterval, limit = 200): Promise<OhlcvResponse> {
  return requestJson<OhlcvResponse>(`/market/ohlcv/${encodeURIComponent(symbol)}?interval=${interval}&limit=${limit}`)
}

export function fetchIndicators(symbol: string, interval: MarketInterval, limit = 200): Promise<IndicatorResponse> {
  return requestJson<IndicatorResponse>(`/market/indicators/${encodeURIComponent(symbol)}?interval=${interval}&limit=${limit}`)
}
