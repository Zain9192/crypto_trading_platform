import { useState } from 'react'
import type { FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

type Request = <T>(path: string, method?: string, body?: unknown) => Promise<T>
type Config = { portfolio_id: number | null; connection_id?: string | null; symbol: string; interval: string; mode: 'paper' | 'sandbox'; min_quote_per_order?: string; max_quote_per_order?: string; max_open_positions?: number; slippage_bps?: number; enabled: boolean; confidence_threshold: string; order_amount: string; max_open_trades: number; stop_loss_pct: string | null; take_profit_pct: string | null }
type Bot = { bot_id: string; config: Config; state: string; failures: number; last_error: string | null; last_result: string | null; last_tick_at: string | null; price_observed_at?: string | null; realized_pnl?: { realized_pnl: string } | null; fees?: { fee_currency: string; amount: string }[]; balances?: { currency: string; free: string; used: string; observed_at: string }[]; sandbox_orders?: { order_id: string; status: string; side: string; amount: string; filled: string; cost: string; last_error: string | null }[]; position?: { unrealized_pnl?: string; quantity: string; entry_price: string; stop_loss_price: string | null; take_profit_price: string | null } | null }
type History = { items: { decision_id: number; signal: string; reason: string; order_status: string | null; quantity: string | null; simulation_price: string | null; created_at: string }[]; next_cursor: number | null }

export default function TradingDashboard({ request }: { request: Request }) {
  const [key] = useState(() => crypto.randomUUID())
  const [newMode, setNewMode] = useState<'paper' | 'sandbox'>('paper')
  const [selected, setSelected] = useState('')
  const [cursor, setCursor] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const cache = useQueryClient()
  const common = { retry: false as const, gcTime: 0 }
  const portfolios = useQuery({ queryKey: ['bot-portfolios', key], queryFn: () => request<{ portfolio_id: number }[]>('/portfolios'), ...common })
  const connections = useQuery({ queryKey: ['bot-connections', key], queryFn: () => request<{ connection_id: string; exchange: string; sandbox: boolean; label: string }[]>('/exchanges'), ...common })
  const bots = useQuery({ queryKey: ['bots', key], queryFn: () => request<Bot[]>('/bots'), refetchInterval: 5000, ...common })
  const detail = useQuery({ queryKey: ['bot', key, selected], queryFn: () => request<Bot>(`/bots/${selected}`), enabled: !!selected, refetchInterval: 5000, ...common })
  const history = useQuery({ queryKey: ['bot-history', key, selected, cursor], queryFn: () => request<History>(`/bots/${selected}/history${cursor ? `?before=${cursor}` : ''}`), enabled: !!selected, refetchInterval: 5000, ...common })
  const bot = detail.data
  async function action(operation: () => Promise<unknown>) {
    setBusy(true); setError('')
    try { await operation(); await Promise.all([cache.invalidateQueries({ queryKey: ['bots', key] }), cache.invalidateQueries({ queryKey: ['bot', key] }), cache.invalidateQueries({ queryKey: ['bot-history', key] })]) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Request failed') }
    finally { setBusy(false) }
  }
  function save(event: FormEvent<HTMLFormElement>, existing?: Bot) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const mode = existing?.config.mode ?? newMode
    const config: Config = { portfolio_id: mode === 'paper' ? (existing?.config.portfolio_id ?? Number(data.get('portfolio'))) : null, connection_id: mode === 'sandbox' ? (existing?.config.connection_id ?? String(data.get('connection'))) : null, symbol: existing?.config.symbol ?? String(data.get('symbol')).toUpperCase(), mode, enabled: data.get('enabled') === 'on', interval: String(data.get('interval')), confidence_threshold: String(data.get('confidence')), order_amount: String(data.get('amount')), max_open_trades: Number(data.get('max')), stop_loss_pct: String(data.get('stop')) || null, take_profit_pct: String(data.get('take')) || null,
      min_quote_per_order: String(data.get('minQuote') ?? existing?.config.min_quote_per_order ?? '1'), max_quote_per_order: String(data.get('maxQuote') ?? existing?.config.max_quote_per_order ?? '1000'), max_open_positions: Number(data.get('positions') ?? existing?.config.max_open_positions ?? 5), slippage_bps: Number(data.get('slippage') ?? existing?.config.slippage_bps ?? 50) }
    void action(async () => { const result = await request<Bot>(existing ? `/bots/${existing.bot_id}` : '/bots', existing ? 'PUT' : 'POST', config); setSelected(result.bot_id); setCursor(null) })
  }
  function fields(config?: Config) {
    const sandbox = (config?.mode ?? newMode) === 'sandbox'
    return <>
      <label>Interval<select name="interval" defaultValue={config?.interval ?? '1d'}>{['1h', '4h', '1d', '1w', '1M'].map(v => <option key={v}>{v}</option>)}</select></label>
      <label>Asset units per buy<input name="amount" type="number" min="0.00000001" max="1000000000" step="0.00000001" defaultValue={config?.order_amount ?? '0.001'} required /></label>
      <label>Minimum confidence (0.5–1)<input name="confidence" type="number" min="0.5" max="1" step="0.01" defaultValue={config?.confidence_threshold ?? '0.7'} required /></label>
      <label>Maximum pending trades<input name="max" type="number" min="1" max="100" defaultValue={config?.max_open_trades ?? 1} required /></label>
      <label>Stop loss % ({sandbox ? 'blank disables' : 'blank uses portfolio setting'})<input name="stop" type="number" min="0.0001" max="99.9999" step="0.0001" defaultValue={config?.stop_loss_pct ?? ''} /></label>
      <label>Take profit % ({sandbox ? 'blank disables' : 'blank uses portfolio setting'})<input name="take" type="number" min="0.0001" step="0.0001" defaultValue={config?.take_profit_pct ?? ''} /></label>
      {sandbox && <>
        <label>Minimum order value (USDT)<input name="minQuote" type="number" min="0.00000001" step="any" defaultValue={config?.min_quote_per_order ?? '1'} required /></label>
        <label>Maximum buy value (USDT)<input name="maxQuote" type="number" min="0.00000001" step="any" defaultValue={config?.max_quote_per_order ?? '1000'} required /></label>
        <label>Maximum account positions<input name="positions" type="number" min="1" max="100" defaultValue={config?.max_open_positions ?? 5} required /></label>
        <label>Price limit distance (basis points)<input name="slippage" type="number" min="1" max="200" defaultValue={config?.slippage_bps ?? 50} required /></label>
      </>}
      <label><input name="enabled" type="checkbox" defaultChecked={config?.enabled ?? false} /> Enable starting this {sandbox ? 'testnet' : 'paper'} bot</label>
    </>
  }
  return <section className="market-panel">
    <p className="eyebrow">Automated spot trading</p><h2>Trading bots</h2>
    <p>Paper USD or Binance Spot Testnet virtual assets. Each bot manages one position at a time, using an activated prediction model and fresh market prices. Stopping pauses monitoring and leaves holdings open.</p>
    <p>Paper fills use the latest USD quote with zero simulated fees. Exit thresholds are checked on worker ticks, not guaranteed execution prices. Testnet uses price-limited immediate-or-cancel orders. Only one unresolved order per testnet account is allowed.</p>
    {(error || bots.error || detail.error || history.error || portfolios.error || connections.error) && <p role="alert" className="error-banner">{error || String(bots.error ?? detail.error ?? history.error ?? portfolios.error ?? connections.error)}</p>}
    <details><summary>Create a bot</summary>
      <label>Trading mode<select value={newMode} onChange={e => setNewMode(e.target.value as 'paper' | 'sandbox')}><option value="paper">Paper USD</option><option value="sandbox">Binance Spot Testnet</option></select></label>
      <form className="portfolio-form" key={newMode} onSubmit={e => save(e)}>
        {newMode === 'paper' ? <label>Portfolio<select name="portfolio" required><option value="">Select a paper portfolio</option>{portfolios.data?.map(p => <option key={p.portfolio_id} value={p.portfolio_id}>{p.portfolio_id}</option>)}</select></label> : <label>Testnet connection<select name="connection" required><option value="">Select a Binance testnet account</option>{connections.data?.filter(c => c.exchange === 'binance' && c.sandbox).map(c => <option key={c.connection_id} value={c.connection_id}>{c.label}</option>)}</select></label>}
        <label>{newMode === 'paper' ? 'USD' : 'USDT'} pair<input name="symbol" placeholder={newMode === 'paper' ? 'BTC/USD' : 'BTC/USDT'} required /></label>
        {fields()}<button disabled={busy}>Save bot</button>
      </form>
    </details>
    <label>Saved bot<select value={selected} onChange={e => { setSelected(e.target.value); setCursor(null); setError('') }}><option value="">Select a bot</option>{bots.data?.map(b => <option key={b.bot_id} value={b.bot_id}>{b.config.mode} · {b.config.symbol} · {b.state}</option>)}</select></label>
    {bot && <>
      <h3>{bot.config.mode} · {bot.config.symbol} · {bot.state}</h3>
      <p>Last result: {bot.last_result ?? 'Not run'} · Consecutive failures: {bot.failures} · Last tick: {bot.last_tick_at ? new Date(bot.last_tick_at).toLocaleString() : 'Never'}</p>
      {bot.last_error && <p role="alert">{bot.last_error}</p>}
      <div className="portfolio-toolbar">
        <button disabled={busy || bot.state !== 'stopped' || !bot.config.enabled} onClick={() => void action(() => request(`/bots/${selected}/control/start`, 'POST'))}>Start</button>
        <button disabled={busy || !['running', 'stopping'].includes(bot.state)} onClick={() => void action(() => request(`/bots/${selected}/control/stop`, 'POST'))}>Stop</button>
        <button disabled={busy || bot.state !== 'error'} onClick={() => void action(() => request(`/bots/${selected}/control/reset`, 'POST'))}>Reset error</button>
        <button disabled={busy || !bot.position || !['stopped', 'error'].includes(bot.state)} onClick={() => void action(() => request(`/bots/${selected}/close-position`, 'POST'))}>Close {bot.config.mode} position</button>
      </div>
      {bot.position && <p>Position: {bot.position.quantity} units · Entry {bot.position.entry_price} · Stop {bot.position.stop_loss_price ?? 'off'} · Take profit {bot.position.take_profit_price ?? 'off'}</p>}
      {bot.state === 'stopped' && <details key={`${bot.bot_id}:${JSON.stringify(bot.config)}`}><summary>Edit bot settings</summary><p>Exit thresholds on an existing position remain fixed at entry.</p><form className="portfolio-form" onSubmit={e => save(e, bot)}>{fields(bot.config)}<button disabled={busy}>Save settings</button></form></details>}
      {bot.config.mode === 'sandbox' && <>
        <p>USDT realized P&amp;L: {bot.realized_pnl?.realized_pnl ?? '0'} · Unrealized: {bot.position?.unrealized_pnl ?? '—'} · Quote observed: {bot.price_observed_at ? new Date(bot.price_observed_at).toLocaleString() : 'unavailable'}. P&amp;L excludes third-currency fees.</p>
        <p>Recorded fees: {bot.fees?.map(f => `${f.amount} ${f.fee_currency}`).join(', ') || 'None'}</p>
        <h3>Testnet account balances</h3>
        <div className="table-wrap"><table><thead><tr><th>Asset</th><th>Free</th><th>Used</th><th>Observed</th></tr></thead><tbody>{bot.balances?.map(b => <tr key={b.currency}><td>{b.currency}</td><td>{b.free}</td><td>{b.used}</td><td>{new Date(b.observed_at).toLocaleString()}</td></tr>)}</tbody></table></div>
        <h3>Recent sandbox orders</h3><p>Unknown outcomes block new orders and continue reconciling. Orders are never automatically resubmitted.</p>
        <div className="table-wrap"><table><thead><tr><th>Client ID</th><th>Status</th><th>Side</th><th>Filled / requested</th><th>Cost</th><th>Actions</th></tr></thead><tbody>{bot.sandbox_orders?.map(o => <tr key={o.order_id}><td>{o.order_id}</td><td>{o.status}{o.last_error && <p>{o.last_error}</p>}</td><td>{o.side}</td><td>{o.filled} / {o.amount}</td><td>{o.cost}</td><td>{['submitting', 'unknown', 'open', 'partially_filled'].includes(o.status) && <><button disabled={busy} onClick={() => void action(() => request(`/bots/${selected}/sandbox/reconcile?order_id=${o.order_id}`, 'POST'))}>Reconcile</button><button disabled={busy} onClick={() => void action(() => request(`/bots/${selected}/sandbox/cancel?order_id=${o.order_id}`, 'POST'))}>Cancel</button></>}</td></tr>)}</tbody></table></div>
      </>}
      <h3>Decisions and fills</h3>
      <div className="table-wrap"><table><thead><tr><th>Time</th><th>Signal</th><th>Result</th><th>Units</th><th>{bot.config.mode === 'paper' ? 'USD' : 'USDT'} price</th></tr></thead><tbody>{history.data?.items.map(item => <tr key={item.decision_id}><td>{new Date(item.created_at).toLocaleString()}</td><td>{item.signal}</td><td>{item.order_status ?? item.reason}</td><td>{item.quantity ?? '—'}</td><td>{item.simulation_price ?? '—'}</td></tr>)}</tbody></table></div>
      {!history.data?.items.length && <p>No decisions yet.</p>}
      <div className="portfolio-toolbar"><button disabled={!cursor} onClick={() => setCursor(null)}>Latest</button><button disabled={!history.data?.next_cursor} onClick={() => setCursor(history.data?.next_cursor ?? null)}>Older</button></div>
    </>}
  </section>
}
