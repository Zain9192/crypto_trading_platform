import { useState } from 'react'
import type { FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

type Request = <T>(path: string, method?: string, body?: unknown) => Promise<T>
type Config = { portfolio_id: number; symbol: string; interval: string; mode: 'paper'; enabled: boolean; confidence_threshold: string; order_amount: string; max_open_trades: number; stop_loss_pct: string | null; take_profit_pct: string | null }
type Bot = { bot_id: string; config: Config; state: string; failures: number; last_error: string | null; last_result: string | null; last_tick_at: string | null; position?: { quantity: string; entry_price: string; stop_loss_price: string | null; take_profit_price: string | null } | null }
type History = { items: { decision_id: number; signal: string; reason: string; order_status: string | null; quantity: string | null; simulation_price: string | null; created_at: string }[]; next_cursor: number | null }

export default function TradingDashboard({ request }: { request: Request }) {
  const [key] = useState(() => crypto.randomUUID())
  const [selected, setSelected] = useState('')
  const [cursor, setCursor] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const cache = useQueryClient()
  const common = { retry: false as const, gcTime: 0 }
  const portfolios = useQuery({ queryKey: ['bot-portfolios', key], queryFn: () => request<{ portfolio_id: number }[]>('/portfolios'), ...common })
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
    const config: Config = { portfolio_id: existing?.config.portfolio_id ?? Number(data.get('portfolio')), symbol: existing?.config.symbol ?? String(data.get('symbol')).toUpperCase(), mode: 'paper', enabled: data.get('enabled') === 'on', interval: String(data.get('interval')), confidence_threshold: String(data.get('confidence')), order_amount: String(data.get('amount')), max_open_trades: Number(data.get('max')), stop_loss_pct: String(data.get('stop')) || null, take_profit_pct: String(data.get('take')) || null }
    void action(async () => { const result = await request<Bot>(existing ? `/bots/${existing.bot_id}` : '/bots', existing ? 'PUT' : 'POST', config); setSelected(result.bot_id); setCursor(null) })
  }
  function fields(config?: Config) {
    return <>
      <label>Interval<select name="interval" defaultValue={config?.interval ?? '1d'}>{['1h', '4h', '1d', '1w', '1M'].map(v => <option key={v}>{v}</option>)}</select></label>
      <label>Asset units per buy<input name="amount" type="number" min="0.00000001" max="1000000000" step="0.00000001" defaultValue={config?.order_amount ?? '0.001'} required /></label>
      <label>Minimum confidence (0.5–1)<input name="confidence" type="number" min="0.5" max="1" step="0.01" defaultValue={config?.confidence_threshold ?? '0.7'} required /></label>
      <label>Maximum pending trades<input name="max" type="number" min="1" max="100" defaultValue={config?.max_open_trades ?? 1} required /></label>
      <label>Stop loss % (blank uses portfolio setting)<input name="stop" type="number" min="0.0001" max="99.9999" step="0.0001" defaultValue={config?.stop_loss_pct ?? ''} /></label>
      <label>Take profit % (blank uses portfolio setting)<input name="take" type="number" min="0.0001" step="0.0001" defaultValue={config?.take_profit_pct ?? ''} /></label>
      <label><input name="enabled" type="checkbox" defaultChecked={config?.enabled ?? false} /> Enable starting this paper bot</label>
    </>
  }
  return <section className="market-panel">
    <p className="eyebrow">Automated paper trading</p><h2>Trading bots</h2>
    <p>Virtual USD only. Each bot manages one position at a time, using an activated prediction model and fresh market prices. Stopping pauses monitoring and leaves holdings open.</p>
    <p>Paper fills use the latest USD quote with zero simulated fees. Exit thresholds are checked on worker ticks, not guaranteed execution prices.</p>
    {(error || bots.error || detail.error || history.error || portfolios.error) && <p role="alert" className="error-banner">{error || String(bots.error ?? detail.error ?? history.error ?? portfolios.error)}</p>}
    <details><summary>Create a bot</summary>
      {!portfolios.data?.length ? <p>Create a paper portfolio first in the Paper portfolio tab.</p> : <form className="portfolio-form" onSubmit={e => save(e)}>
        <label>Portfolio<select name="portfolio">{portfolios.data.map(p => <option key={p.portfolio_id} value={p.portfolio_id}>{p.portfolio_id}</option>)}</select></label>
        <label>USD pair<input name="symbol" placeholder="BTC/USD" pattern="[A-Za-z0-9]{1,20}/[Uu][Ss][Dd]" required /></label>
        {fields()}<button disabled={busy}>Save bot</button>
      </form>}
    </details>
    <label>Saved bot<select value={selected} onChange={e => { setSelected(e.target.value); setCursor(null); setError('') }}><option value="">Select a bot</option>{bots.data?.map(b => <option key={b.bot_id} value={b.bot_id}>{b.config.symbol} · {b.state}</option>)}</select></label>
    {bot && <>
      <h3>{bot.config.symbol} · {bot.state}</h3>
      <p>Last result: {bot.last_result ?? 'Not run'} · Consecutive failures: {bot.failures} · Last tick: {bot.last_tick_at ? new Date(bot.last_tick_at).toLocaleString() : 'Never'}</p>
      {bot.last_error && <p role="alert">{bot.last_error}</p>}
      <div className="portfolio-toolbar">
        <button disabled={busy || bot.state !== 'stopped' || !bot.config.enabled} onClick={() => void action(() => request(`/bots/${selected}/control/start`, 'POST'))}>Start</button>
        <button disabled={busy || !['running', 'stopping'].includes(bot.state)} onClick={() => void action(() => request(`/bots/${selected}/control/stop`, 'POST'))}>Stop</button>
        <button disabled={busy || bot.state !== 'error'} onClick={() => void action(() => request(`/bots/${selected}/control/reset`, 'POST'))}>Reset error</button>
        <button disabled={busy || !bot.position || !['stopped', 'error'].includes(bot.state)} onClick={() => void action(() => request(`/bots/${selected}/close-position`, 'POST'))}>Close paper position</button>
      </div>
      {bot.position && <p>Position: {bot.position.quantity} units · Entry ${bot.position.entry_price} · Stop ${bot.position.stop_loss_price ?? 'off'} · Take profit ${bot.position.take_profit_price ?? 'off'}</p>}
      {bot.state === 'stopped' && <details key={`${bot.bot_id}:${JSON.stringify(bot.config)}`}><summary>Edit bot settings</summary><p>Exit thresholds on an existing position remain fixed at entry.</p><form className="portfolio-form" onSubmit={e => save(e, bot)}>{fields(bot.config)}<button disabled={busy}>Save settings</button></form></details>}
      <h3>Decisions and fills</h3>
      <div className="table-wrap"><table><thead><tr><th>Time</th><th>Signal</th><th>Result</th><th>Units</th><th>USD price</th></tr></thead><tbody>{history.data?.items.map(item => <tr key={item.decision_id}><td>{new Date(item.created_at).toLocaleString()}</td><td>{item.signal}</td><td>{item.order_status ?? item.reason}</td><td>{item.quantity ?? '—'}</td><td>{item.simulation_price ?? '—'}</td></tr>)}</tbody></table></div>
      {!history.data?.items.length && <p>No decisions yet.</p>}
      <div className="portfolio-toolbar"><button disabled={!cursor} onClick={() => setCursor(null)}>Latest</button><button disabled={!history.data?.next_cursor} onClick={() => setCursor(history.data?.next_cursor ?? null)}>Older</button></div>
    </>}
  </section>
}
