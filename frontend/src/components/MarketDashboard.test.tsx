import '@testing-library/jest-dom/vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import * as api from '../api/market'
import MarketDashboard from './MarketDashboard'

vi.mock('../api/market', () => ({ fetchTopAssets: vi.fn(), fetchOhlcv: vi.fn(), fetchIndicators: vi.fn() }))
vi.mock('../hooks/useMarketSocket', () => ({ useMarketSocket: vi.fn() }))
vi.mock('./CandlestickChart', () => ({ default: () => <div>Chart</div> }))
function setup() {
  vi.mocked(api.fetchTopAssets).mockResolvedValue({
    items: [{ id: 'btc', symbol: 'BTC', name: 'Bitcoin' }],
    count: 1, cached: false, refresh_seconds: 2, source: 'coingecko',
  })
  vi.mocked(api.fetchOhlcv).mockResolvedValue({
    items: [], count: 0, symbol: 'BTC', interval: '1d', cached: false, source: 'binance',
  })
  vi.mocked(api.fetchIndicators).mockResolvedValue({
    items: [], count: 0, symbol: 'BTC', interval: '1d', source: 'calculated',
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })
  render(<QueryClientProvider client={client}><MarketDashboard /></QueryClientProvider>)
  return client
}
afterEach(() => { cleanup(); vi.clearAllMocks(); vi.useRealTimers() })
it('uses configured cadence to refresh assets, candles and indicators', async () => {
  vi.useFakeTimers()
  const client = setup()
  await act(async () => { await vi.advanceTimersByTimeAsync(100) })
  expect(screen.getByText('2s refresh')).toBeInTheDocument()
  const requests = [api.fetchTopAssets, api.fetchOhlcv, api.fetchIndicators]
  const before = requests.map(fn => vi.mocked(fn).mock.calls.length)
  await act(async () => { await vi.advanceTimersByTimeAsync(2100) })
  requests.forEach((fn, index) => {
    expect(vi.mocked(fn).mock.calls.length).toBeGreaterThan(before[index])
  })
  client.clear()
})
it('requests candles and indicators when the chart interval changes', async () => {
  const client = setup()
  await screen.findByText('2s refresh')
  fireEvent.click(screen.getByRole('button', { name: '1W' }))
  expect(api.fetchOhlcv).toHaveBeenLastCalledWith('BTC', '1w', 200)
  expect(api.fetchIndicators).toHaveBeenLastCalledWith('BTC', '1w', 200)
  client.clear()
})
