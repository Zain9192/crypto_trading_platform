import '@testing-library/jest-dom/vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import ExchangeDashboard from './ExchangeDashboard'

const row = { connection_id: 'c1', exchange: 'binance', label: 'Research', sandbox: true, read_only: true }
function mount(request: ReturnType<typeof vi.fn>) {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ExchangeDashboard request={request as never} /></QueryClientProvider>)
}
afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('saves credentials, clears inputs and displays normalized balances', async () => {
  let saved = false
  const request = vi.fn(async (path: string, method?: string) => {
    if (path === '/exchanges/capabilities') return [{ exchange: 'binance', sandbox: true, note: 'Spot testnet' }]
    if (path === '/exchanges' && method === 'POST') { saved = true; return row }
    if (path === '/exchanges') return saved ? [row] : []
    if (path.endsWith('/balances')) return [{ currency: 'BTC', free: '1.2', used: '0.3', total: '1.5' }]
    return {}
  })
  mount(request)
  fireEvent.change(screen.getByLabelText('Connection label'), { target: { value: 'Research' } })
  fireEvent.change(screen.getByLabelText('API key'), { target: { value: 'ephemeral-test-input' } })
  fireEvent.change(screen.getByLabelText('API secret / private key'), { target: { value: 'ephemeral-test-secret' } })
  fireEvent.click(screen.getByRole('button', { name: 'Verify and save connection' }))
  expect(await screen.findByText('1.2')).toBeInTheDocument()
  expect(screen.getByLabelText('API key')).toHaveValue('')
  expect(screen.getByLabelText('API secret / private key')).toHaveValue('')
  expect(screen.getByText(/stored encrypted/)).toBeInTheDocument()
  expect(request).toHaveBeenCalledWith('/exchanges', 'POST', expect.objectContaining({ sandbox: true, exchange: 'binance' }))
})

it('shows provider sandbox limits and does not offer production trading', async () => {
  const request = vi.fn(async (path: string) => path.includes('capabilities') ? [{ exchange: 'kraken', sandbox: false, note: 'Spot UAT requires separate access' }] : [])
  mount(request)
  fireEvent.change(screen.getByLabelText('Exchange'), { target: { value: 'kraken' } })
  await screen.findByText('Spot UAT requires separate access')
  expect(screen.getByLabelText('Environment')).toHaveValue('production')
  expect(screen.queryByRole('option', { name: 'Spot testnet · read-only' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /place order/i })).not.toBeInTheDocument()
})

it('reports provider errors and supports credential replacement and removal', async () => {
  let removed = false
  const request = vi.fn(async (path: string, method?: string) => {
    if (path === '/exchanges') return removed ? [] : [row]
    if (path.endsWith('/capabilities')) return []
    if (path.endsWith('/balances')) throw new Error('Exchange unavailable or request timed out')
    if (method === 'DELETE') removed = true
    return row
  })
  mount(request)
  await screen.findByRole('option', { name: /Research/ })
  fireEvent.change(screen.getByLabelText('Selected connection'), { target: { value: 'c1' } })
  expect(await screen.findByRole('alert')).toHaveTextContent('Exchange unavailable')
  fireEvent.change(screen.getByLabelText('New API key'), { target: { value: 'new-ephemeral-key' } })
  fireEvent.change(screen.getByLabelText('New API secret / private key'), { target: { value: 'new-ephemeral-secret' } })
  fireEvent.click(screen.getByRole('button', { name: 'Verify and replace credentials' }))
  await waitFor(() => expect(request).toHaveBeenCalledWith('/exchanges/c1/credentials', 'PUT', expect.any(Object)))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Remove connection' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Remove connection' }))
  await screen.findByText('No exchange connections yet.')
  expect(request).toHaveBeenCalledWith('/exchanges/c1', 'DELETE')
})

it('retrieves prices, bounded trade history and order status', async () => {
  const request = vi.fn(async (path: string) => {
    if (path === '/exchanges') return [row]
    if (path.endsWith('/capabilities') || path.endsWith('/balances')) return []
    if (path.includes('/price?')) return { price: '123.45', observed_at: '2026-09-14T00:00:00Z' }
    if (path.includes('/trades?')) return { items: [{ trade_id: 'trade-1', symbol: 'BTC/USDT', side: 'buy', amount: '1', price: '123', executed_at: '2026-09-14T00:00:00Z' }], possibly_truncated: true }
    return { order_id: 'order-1', symbol: 'BTC/USDT', side: 'buy', status: 'closed', amount: '1', filled: '1', price: '123' }
  })
  mount(request)
  await screen.findByRole('option', { name: /Research/ })
  fireEvent.change(screen.getByLabelText('Selected connection'), { target: { value: 'c1' } })
  fireEvent.change(screen.getByLabelText('Market symbol'), { target: { value: 'BTC/USDT' } })
  fireEvent.click(screen.getByRole('button', { name: 'Load price and trades' }))
  expect(await screen.findByText('trade-1 · buy')).toBeInTheDocument()
  expect(screen.getByText(/bounded exchange history window/)).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Order market symbol'), { target: { value: 'BTC/USDT' } })
  fireEvent.change(screen.getByLabelText('Exchange order ID'), { target: { value: 'order-1' } })
  fireEvent.click(screen.getByRole('button', { name: 'Look up order' }))
  expect(await screen.findByText('closed')).toBeInTheDocument()
})
