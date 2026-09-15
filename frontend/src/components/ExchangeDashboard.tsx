import { useState } from 'react'
import type { FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

type Request = <T>(path: string, method?: string, body?: unknown) => Promise<T>
interface Connection { connection_id: string; exchange: string; label: string; sandbox: boolean; read_only: true }
interface Capability { exchange: string; sandbox: boolean; note: string }
interface Balance { currency: string; free: string; used: string; total: string }
interface Trade { trade_id: string; symbol: string; side: string; amount: string; price: string; executed_at: string }
interface Order { order_id: string; symbol: string; side: string; status: string; amount: string; filled: string; price: string | null }

export default function ExchangeDashboard({ request }: { request: Request }) {
  const cache = useQueryClient()
  const [cacheKey] = useState(() => crypto.randomUUID())
  const [selected, setSelected] = useState('')
  const [exchange, setExchange] = useState('binance')
  const [sandbox, setSandbox] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [filter, setFilter] = useState<{ symbol: string; since: string; limit: string } | null>(null)
  const [order, setOrder] = useState<Order | null>(null)
  const connections = useQuery({ queryKey: ['exchanges', cacheKey], queryFn: () => request<Connection[]>('/exchanges'), retry: false, gcTime: 0 })
  const capabilities = useQuery({ queryKey: ['exchange-capabilities', cacheKey], queryFn: () => request<Capability[]>('/exchanges/capabilities'), retry: false, gcTime: 0 })
  const connection = connections.data?.find(row => row.connection_id === selected)
  const balances = useQuery({ queryKey: ['exchange-balances', cacheKey, selected], queryFn: () => request<Balance[]>(`/exchanges/${selected}/balances`), enabled: Boolean(connection), retry: false, gcTime: 0 })
  const query = filter ? new URLSearchParams({ symbol: filter.symbol, limit: filter.limit, ...(filter.since ? { since: new Date(filter.since + ':00Z').toISOString() } : {}) }).toString() : ''
  const trades = useQuery({ queryKey: ['exchange-trades', cacheKey, selected, query], queryFn: () => request<{ items: Trade[]; possibly_truncated: boolean }>(`/exchanges/${selected}/trades?${query}`), enabled: Boolean(connection && filter), retry: false, gcTime: 0 })
  const price = useQuery({ queryKey: ['exchange-price', cacheKey, selected, filter?.symbol], queryFn: () => request<{ price: string; observed_at: string }>(`/exchanges/${selected}/price?symbol=${encodeURIComponent(filter?.symbol ?? '')}`), enabled: Boolean(connection && filter), retry: false, gcTime: 0 })

  async function act(operation: () => Promise<unknown>, success: string) {
    setBusy(true); setError(''); setNotice('')
    try { await operation(); setNotice(success) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Exchange request failed') }
    finally { setBusy(false) }
  }
  function credentials(form: HTMLFormElement) {
    const values = new FormData(form)
    return { api_key: String(values.get('api_key') ?? ''), api_secret: String(values.get('api_secret') ?? ''), passphrase: values.get('passphrase') || null }
  }
  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const label = String(new FormData(form).get('label') ?? '')
    void act(async () => {
      const saved = await request<Connection>('/exchanges', 'POST', { exchange, label, sandbox, credentials: credentials(form) })
      await cache.cancelQueries({ queryKey: ['exchanges', cacheKey] })
      cache.setQueryData<Connection[]>(['exchanges', cacheKey], old => [...(old ?? []).filter(c => c.connection_id !== saved.connection_id), saved])
      form.reset(); setSelected(saved.connection_id); setFilter(null); setOrder(null)
      await connections.refetch()
    }, 'Connection verified and saved. Credentials are encrypted and never returned.')
  }
  function replace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    void act(async () => { await request(`/exchanges/${selected}/credentials`, 'PUT', credentials(form)); form.reset(); await balances.refetch() }, 'Replacement credentials verified and saved.')
  }
  function inspect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const next = { symbol: String(data.get('symbol')), since: String(data.get('since')), limit: String(data.get('limit')) }
    if (filter && JSON.stringify(next) === JSON.stringify(filter)) { void trades.refetch(); void price.refetch() }
    else setFilter(next)
  }
  function lookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    setOrder(null)
    void act(async () => setOrder(await request<Order>(`/exchanges/${selected}/orders/${encodeURIComponent(String(data.get('order_id')))}?symbol=${encodeURIComponent(String(data.get('symbol')))}`)), 'Order retrieved.')
  }
  const failure = error || connections.error?.message || capabilities.error?.message || balances.error?.message || trades.error?.message || price.error?.message
  return <section className="portfolio-shell">
    <div className="portfolio-toolbar"><h2>Exchange connections</h2><span className="live-pill">Read-only account access</span><button disabled={busy} onClick={() => { void connections.refetch(); void capabilities.refetch() }}>Refresh connections</button></div>
    <p className="subtitle">Inspect exchange balances, prices, orders and recent trades. Paper balances stay separate. This screen cannot submit or cancel exchange orders.</p>
    {failure && <p role="alert" className="error-banner">{failure}</p>}
    {notice && <p role="status" className="success-banner">{notice}</p>}
    {connections.isPending && <p role="status">Loading exchange connections…</p>}
    <div className="portfolio-columns">
      <section className="market-panel portfolio-card"><h3>Add connection</h3>
        <form className="portfolio-form" onSubmit={create}><fieldset disabled={busy}>
          <label>Exchange<select value={exchange} onChange={e => { setExchange(e.target.value); if (e.target.value !== 'binance') setSandbox(false) }}><option value="binance">Binance</option><option value="coinbase">Coinbase Advanced Trade</option><option value="kraken">Kraken</option></select></label>
          <p className="muted">{capabilities.data?.find(c => c.exchange === exchange)?.note}</p>
          <label>Environment<select value={sandbox ? 'sandbox' : 'production'} onChange={e => setSandbox(e.target.value === 'sandbox')}><option value="production">Production · read-only</option>{exchange === 'binance' && <option value="sandbox">Spot testnet · read-only</option>}</select></label>
          <label>Connection label<input name="label" required maxLength={80} placeholder="My research account" /></label>
          <label>API key<input name="api_key" type="password" autoComplete="off" required /></label>
          <label>API secret / private key<textarea name="api_secret" autoComplete="off" required rows={3} /></label>
          <label>Passphrase (if required)<input name="passphrase" type="password" autoComplete="off" /></label>
          <p className="muted">Use account-read permission with trading and withdrawals disabled. For Coinbase, paste the issued key name and EC private key. Binance testnet needs separate testnet keys.</p>
          <button className="primary-button">Verify and save connection</button>
        </fieldset></form>
      </section>
      <section className="market-panel portfolio-card"><h3>Saved accounts</h3>
        {connections.data?.length === 0 && <p>No exchange connections yet.</p>}
        <label>Selected connection<select disabled={busy} value={selected} onChange={e => { setSelected(e.target.value); setFilter(null); setOrder(null); setError(''); setNotice('') }}>
          <option value="">Choose an account</option>{connections.data?.map(c => <option key={c.connection_id} value={c.connection_id}>{c.label} · {c.exchange} · {c.sandbox ? 'testnet' : 'production'}</option>)}
        </select></label>
        {connection && <>
          <p>Credentials: •••••••• · stored encrypted</p>
          <div className="portfolio-toolbar">
            <button disabled={busy} onClick={() => void act(() => request(`/exchanges/${selected}/verify`, 'POST'), 'Connection verified.')}>Verify connection</button>
            <button disabled={busy} onClick={() => void balances.refetch()}>Refresh balances</button>
            <button disabled={busy} onClick={() => void act(async () => { await request(`/exchanges/${selected}`, 'DELETE'); setSelected(''); setFilter(null); setOrder(null); await connections.refetch() }, 'Connection removed locally. Revoke its key at the exchange if no longer needed.')}>Remove connection</button>
          </div>
          <h3>Replace credentials</h3><form className="portfolio-form" onSubmit={replace}><fieldset disabled={busy}>
            <label>New API key<input name="api_key" type="password" autoComplete="off" required /></label>
            <label>New API secret / private key<textarea name="api_secret" autoComplete="off" required rows={3} /></label>
            <label>New passphrase (if required)<input name="passphrase" type="password" autoComplete="off" /></label>
            <button>Verify and replace credentials</button>
          </fieldset></form>
        </>}
      </section>
    </div>
    {connection && <>
      <section className="market-panel"><div className="section-heading"><h3>Exchange balances</h3><span>{connection.label} · {connection.sandbox ? 'Testnet' : 'Production'} · Read-only</span></div><div className="market-table-wrap"><table className="market-table"><thead><tr><th>Currency</th><th>Available</th><th>Used</th><th>Total</th></tr></thead><tbody>
        {balances.isPending ? <tr><td colSpan={4}>Loading balances…</td></tr> : balances.error ? <tr><td colSpan={4}>Balances unavailable.</td></tr> : balances.data?.length ? balances.data.map(b => <tr key={b.currency}><td>{b.currency}</td><td>{b.free}</td><td>{b.used}</td><td>{b.total}</td></tr>) : <tr><td colSpan={4}>No nonzero balances.</td></tr>}
      </tbody></table></div></section>
      <div className="portfolio-columns">
        <section className="market-panel portfolio-card"><h3>Price & recent trades</h3><form className="portfolio-form" onSubmit={inspect}><fieldset disabled={busy}>
          <label>Market symbol<input name="symbol" pattern="[A-Z0-9]+/[A-Z0-9]+" placeholder={connection.exchange === 'binance' ? 'BTC/USDT' : 'BTC/USD'} required /></label>
          <label>Trades since (UTC)<input name="since" type="datetime-local" /></label>
          <label>Result limit<select name="limit" defaultValue="50"><option>25</option><option>50</option><option>100</option></select></label>
          <button>Load price and trades</button>
        </fieldset></form>
        {price.data && <p>Latest {filter?.symbol}: {price.data.price} · observed {new Date(price.data.observed_at).toLocaleString()}</p>}
        </section>
        <section className="market-panel portfolio-card"><h3>Find exchange order</h3><form className="portfolio-form" onSubmit={lookup}><fieldset disabled={busy}>
          <label>Order market symbol<input name="symbol" pattern="[A-Z0-9]+/[A-Z0-9]+" required placeholder="BTC/USD" /></label>
          <label>Exchange order ID<input name="order_id" required maxLength={200} /></label><button>Look up order</button>
        </fieldset></form>
        {order && <dl><dt>Order</dt><dd>{order.order_id}</dd><dt>Status</dt><dd>{order.status}</dd><dt>Market / side</dt><dd>{order.symbol} · {order.side}</dd><dt>Filled / amount</dt><dd>{order.filled} / {order.amount}</dd><dt>Price</dt><dd>{order.price ?? 'Market order'}</dd></dl>}
        </section>
      </div>
      {filter && <section className="market-panel"><div className="section-heading"><h3>Recent exchange trades</h3><span>{filter.symbol}</span></div>
        {trades.data?.possibly_truncated && <p role="status" className="error-banner">Result limit reached. This is a bounded exchange history window, not a complete account export.</p>}
        <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Time</th><th>Trade / side</th><th>Amount</th><th>Price</th></tr></thead><tbody>
          {trades.isPending ? <tr><td colSpan={4}>Loading trades…</td></tr> : trades.error ? <tr><td colSpan={4}>Trades unavailable.</td></tr> : trades.data?.items.length ? trades.data.items.map(t => <tr key={t.trade_id}><td>{new Date(t.executed_at).toLocaleString()}</td><td>{t.trade_id} · {t.side}</td><td>{t.amount}</td><td>{t.price}</td></tr>) : <tr><td colSpan={4}>No trades returned for this query.</td></tr>}
        </tbody></table></div></section>}
    </>}
  </section>
}
