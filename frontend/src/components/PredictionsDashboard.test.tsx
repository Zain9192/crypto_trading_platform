import '@testing-library/jest-dom/vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import PredictionsDashboard, { COINS } from './PredictionsDashboard'
import type { Forecast } from './PredictionsDashboard'

const forecast = (symbol: string, direction: Forecast['direction'], expected_return: number): Forecast => ({
  symbol, interval: '1d', quote_asset: 'USDT', model_version: `${symbol}-v1`,
  as_of: '2026-11-13T00:00:00Z', forecast_for: '2026-11-15T00:00:00Z', generated_at: '2026-11-14T12:00:00Z',
  current_price: 65000, predicted_price: 65000 * (1 + expected_return), direction,
  up_probability: direction === 'up' ? 0.7 : 0.3, confidence: 0.71, confidence_kind: 'uncalibrated',
  expected_return, estimated_risk: 0.025, validation_error_p95: 0.05, drift: { status: 'review' },
})
function mount(request: ReturnType<typeof vi.fn>) {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><PredictionsDashboard request={request as never} /></QueryClientProvider>)
}
afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('shows the forecast card, model versions and ranking', async () => {
  const request = vi.fn(async (path: string, method?: string, body?: unknown) => {
    if (path === '/predictions/BTC?interval=1d') return forecast('BTC', 'down', -0.012)
    if (path === '/predictions/models/BTC?interval=1d') return [{ version: 'BTC-v1', algorithm: 'ensemble', trained_at: '2026-11-14T10:00:00Z', is_active: true }]
    if (path === '/predictions/opportunities' && method === 'POST') {
      expect(body).toEqual({ symbols: ['BTC', 'ETH', 'SOL', 'BNB', 'XRP'], interval: '1d' })
      return { items: [{ forecast: forecast('ETH', 'up', 0.02), score: 0.4 }, { forecast: forecast('BTC', 'down', -0.012), score: -0.1 }], unavailable: { SOL: 'no model', BNB: 'no model', XRP: 'no model' } }
    }
    throw new Error(`unexpected ${path}`)
  })
  mount(request)
  expect(await screen.findByText('▼ DOWN')).toBeInTheDocument()
  expect(screen.getByText('-1.20%')).toBeInTheDocument()
  expect(screen.getByText('71.0%')).toBeInTheDocument()
  expect(screen.getByText('review')).toBeInTheDocument()
  expect(await screen.findByText('Active')).toBeInTheDocument()
  expect(within(screen.getByLabelText('Interval')).getAllByRole('option').map(o => o.textContent)).toEqual(['1h', '4h', '1d', '1w'])
  const picker = screen.getByRole('combobox', { name: 'Symbol' })
  expect(picker).toHaveTextContent('BTC')
  fireEvent.click(picker)
  const coins = within(screen.getByRole('listbox')).getAllByRole('option').map(o => o.textContent?.replace('✓', ''))
  expect(coins).toEqual(COINS)
  expect(coins).toHaveLength(20)
  fireEvent.keyDown(picker, { key: 'Escape' })
  expect(screen.queryByRole('listbox')).toBeNull()

  fireEvent.click(screen.getByRole('button', { name: 'Rank on 1d' }))
  expect(await screen.findByText('No active model: SOL, BNB, XRP')).toBeInTheDocument()
  const first = screen.getAllByRole('row').find(row => row.firstElementChild?.textContent === '1')
  expect(first).toBeDefined()
  expect(within(first!).getByText('ETH')).toBeInTheDocument()
})

it('explains when no active model exists', async () => {
  const request = vi.fn(async (path: string) => {
    if (path.startsWith('/predictions/models/')) return []
    throw new Error('No active model for DOGE 1d')
  })
  mount(request)
  await screen.findByText(/Train and activate a model for BTC 1d/)
  fireEvent.click(screen.getByRole('combobox', { name: 'Symbol' }))
  fireEvent.click(screen.getByRole('option', { name: 'DOGE' }))
  expect(await screen.findByText(/Train and activate a model for DOGE 1d/)).toBeInTheDocument()
  expect(request).toHaveBeenCalledWith('/predictions/DOGE?interval=1d')
  expect(await screen.findByText('No trained versions yet.')).toBeInTheDocument()
})
