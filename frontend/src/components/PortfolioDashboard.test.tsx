import '@testing-library/jest-dom/vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import PortfolioDashboard from './PortfolioDashboard'
import PortfolioAccess from './PortfolioAccess'

const snapshot = {
  portfolio_id: 1, mode: 'paper', initial_cash: '1000', cash_balance: '798', available_cash: '798', reserved_cash: '0',
  total_value: '1038', realized_pnl: '0', unrealized_pnl: '38', total_pnl: '38', cash_allocation_pct: '76.8786',
  valuation_complete: true, unpriced_symbols: [], pending_orders: [],
  holdings: [{ symbol: 'BTC', quantity: '2', available_quantity: '2', average_cost: '101', cost_basis: '202', market_value: '240', unrealized_pnl: '38', allocation_pct: '23.1214', price_as_of: null }],
  risk_settings: { min_investment: '1', max_investment: '10000', max_open_positions: 10, max_open_trades: 10, stop_loss_pct: '5', take_profit_pct: '10' },
}
function mount(element: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{element}</QueryClientProvider>)
}
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })
function fields() {
  fireEvent.change(screen.getByLabelText('Asset symbol'), { target: { value: 'BTC' } })
  fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '1' } })
  fireEvent.change(screen.getByLabelText('Simulation price (USD)'), { target: { value: '100' } })
}
it('shows incomplete valuations without inventing zero', async () => {
  const request = vi.fn(async (path: string) => path === '/portfolios' ? [{ portfolio_id: 1 }] : path.includes('/trades') ? { items: [], next_cursor: null } : { ...snapshot, total_value: null, unrealized_pnl: null, total_pnl: null, valuation_complete: false, unpriced_symbols: ['BTC'] })
  mount(<PortfolioDashboard request={request as never} />)
  expect(await screen.findByText(/Valuation incomplete/)).toBeInTheDocument()
  expect(screen.getAllByText('Unavailable')).toHaveLength(3)
  expect(screen.getByText('No completed paper trades.')).toBeInTheDocument()
})
it('creates a virtual portfolio and reserves, fills and cancels trades', async () => {
  let exists = false
  let pending: object[] = []
  const request = vi.fn(async (path: string, method?: string, body?: unknown) => {
    if (path === '/portfolios') { if (method === 'POST') exists = true; return exists ? [{ portfolio_id: 1 }] : [] }
    if (path.endsWith('/orders') && method === 'POST') { pending = [{ ...(body as object), order_id: 'order-1', stop_loss_price: '95', take_profit_price: '110' }]; return pending[0] }
    if (path.endsWith('/fill') || path.endsWith('/cancel')) { pending = []; return {} }
    if (path.includes('/trades')) return { items: [], next_cursor: null }
    return { ...snapshot, pending_orders: pending }
  })
  mount(<PortfolioDashboard request={request as never} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Create paper portfolio' }))
  await screen.findByRole('heading', { name: 'New paper trade' })
  expect(request).toHaveBeenCalledWith('/portfolios', 'POST', { initial_cash: '10000' })
  fields(); fireEvent.click(screen.getByRole('button', { name: 'Reserve paper trade' }))
  await screen.findByRole('button', { name: 'Fill paper trade' })
  expect(request).toHaveBeenCalledWith('/portfolios/1/orders', 'POST', expect.objectContaining({ quantity: '1', simulation_price: '100', client_order_id: expect.any(String) }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Fill paper trade' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Fill paper trade' }))
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Fill paper trade' })).not.toBeInTheDocument())
  await waitFor(() => expect(screen.getByRole('button', { name: 'Reserve paper trade' })).toBeEnabled())
  fields(); fireEvent.click(screen.getByRole('button', { name: 'Reserve paper trade' }))
  await screen.findByRole('button', { name: 'Cancel' })
  await waitFor(() => expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  await waitFor(() => expect(request).toHaveBeenCalledWith('/portfolios/1/orders/order-1/cancel', 'POST'))
})
it('keeps the retry key after an uncertain reservation and shows risk errors', async () => {
  const request = vi.fn(async (path: string, method?: string, _body?: unknown) => {
    if (path === '/portfolios') return [{ portfolio_id: 1 }]
    if (path.includes('/trades')) return { items: [], next_cursor: null }
    if (method === 'POST') throw new Error('Insufficient available cash')
    return snapshot
  })
  mount(<PortfolioDashboard request={request as never} />)
  await screen.findByRole('heading', { name: 'New paper trade' })
  fields(); fireEvent.click(screen.getByRole('button', { name: 'Reserve paper trade' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Insufficient available cash')
  fireEvent.click(screen.getByRole('button', { name: 'Reserve paper trade' }))
  await waitFor(() => expect(request.mock.calls.filter(c => c[1] === 'POST')).toHaveLength(2))
  const calls = request.mock.calls.filter(c => c[1] === 'POST') as [string, string, { client_order_id: string }][]
  expect(calls[0][2].client_order_id).toBe(calls[1][2].client_order_id)
})
it('saves risk settings and disables thresholds with blank fields', async () => {
  const request = vi.fn(async (path: string) => path === '/portfolios' ? [{ portfolio_id: 1 }] : path.includes('/trades') ? { items: [], next_cursor: null } : snapshot)
  mount(<PortfolioDashboard request={request as never} />)
  await screen.findByRole('heading', { name: 'Risk settings' })
  fireEvent.change(screen.getByLabelText('Stop-loss % (blank disables)'), { target: { value: '' } })
  fireEvent.change(screen.getByLabelText('Maximum open positions'), { target: { value: '3' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save risk settings' }))
  await waitFor(() => expect(request).toHaveBeenCalledWith('/portfolios/1/risk', 'PUT', expect.objectContaining({ stop_loss_pct: null, max_open_positions: 3 })))
})
it('signs in without storing tokens and clears the portfolio on sign out', async () => {
  const store = vi.spyOn(Storage.prototype, 'setItem')
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => url.endsWith('/login') ? { access_token: 'test-access', refresh_token: 'test-refresh', expires_in: 900 } : url.endsWith('/portfolios') ? [] : {} })))
  mount(<PortfolioAccess />)
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'user@example.com' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'example-password' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  await screen.findByRole('button', { name: 'Create paper portfolio' })
  expect(store).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
  await screen.findByRole('button', { name: 'Sign in' })
  expect(screen.queryByRole('heading', { name: 'Portfolio overview' })).not.toBeInTheDocument()
})

it('keeps the session when risk validation rejects a request after token refresh', async () => {
  let refreshed = false
  const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
    let status = 200
    let payload: unknown = {}
    if (url.endsWith('/login')) payload = { access_token: 'expired-access', refresh_token: 'old-refresh', expires_in: 900 }
    else if (url.endsWith('/refresh')) { refreshed = true; payload = { access_token: 'renewed-access', refresh_token: 'new-refresh', expires_in: 900 } }
    else if (url.endsWith('/portfolios')) payload = [{ portfolio_id: 1 }]
    else if (url.includes('/trades')) payload = { items: [], next_cursor: null }
    else if (url.endsWith('/orders')) {
      status = refreshed ? 422 : 401
      payload = { detail: refreshed ? 'Investment including fee is outside configured limits' : 'Expired token' }
      if (refreshed) expect((options?.headers as Record<string, string>).Authorization).toBe('Bearer renewed-access')
    } else payload = snapshot
    return { ok: status === 200, status, json: async () => payload }
  })
  vi.stubGlobal('fetch', fetchMock)
  mount(<PortfolioAccess />)
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'user@example.com' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'example-password' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  await screen.findByRole('heading', { name: 'New paper trade' })
  fields(); fireEvent.click(screen.getByRole('button', { name: 'Reserve paper trade' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Investment including fee is outside configured limits')
  expect(screen.getByRole('heading', { name: 'Portfolio overview' })).toBeInTheDocument()
  expect(fetchMock.mock.calls.filter(call => call[0].endsWith('/refresh'))).toHaveLength(1)
})
