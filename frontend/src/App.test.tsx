import '@testing-library/jest-dom/vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from './App'

const assetsResponse = {
  items: [{ id: 'bitcoin', symbol: 'BTC', name: 'Bitcoin', current_price: 60000, market_cap_rank: 1 }],
  count: 1,
  cached: true,
  refresh_seconds: 30,
  source: 'coingecko',
}

function mockResponse(url: string) {
  if (url.includes('/ohlcv/')) {
    return { symbol: 'BTC', interval: '1d', items: [], count: 0, cached: true, source: 'binance' }
  }
  if (url.includes('/indicators/')) {
    return { symbol: 'BTC', interval: '1d', items: [], count: 0, source: 'calculated' }
  }
  return assetsResponse
}

afterEach(() => vi.restoreAllMocks())

describe('App', () => {
  it('renders the project and market headings', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => ({
      ok: true,
      json: async () => mockResponse(String(input)),
    })))
    vi.stubGlobal('WebSocket', undefined)
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    )

    expect(screen.getByRole('heading', { name: /ai crypto trading platform/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /top 50 cryptocurrencies/i })).toBeInTheDocument()
  })
})
