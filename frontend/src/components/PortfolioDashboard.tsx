import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { History, PaperRequest, Portfolio, RiskSettings } from '../api/portfolio'

type Request = <T>(path: string, method?: string, body?: unknown) => Promise<T>
const usd = (value: string | null) => value === null ? 'Unavailable' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(Number(value))
const pct = (value: string | null) => value === null ? '—' : `${Number(value).toFixed(2)}%`
const inputNumber = { type: 'number', step: '0.00000001', min: '0.00000001', required: true } as const

export default function PortfolioDashboard({ request }: { request: Request }) {
  // Separate cache identity for every signed-in mount; another user cannot see prior data.
  const [sessionKey] = useState(() => crypto.randomUUID())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [cursor, setCursor] = useState<number | null>(null)
  const [riskRevision, setRiskRevision] = useState(0)
  const orderAttempt = useRef<{ fingerprint: string; id: string } | null>(null)
  const list = useQuery({ queryKey: ['portfolios', sessionKey], queryFn: () => request<{ portfolio_id: number }[]>('/portfolios'), retry: false, gcTime: 0 })
  const id = list.data?.[0]?.portfolio_id
  const portfolio = useQuery({ queryKey: ['portfolio', sessionKey, id], queryFn: () => request<Portfolio>(`/portfolios/${id}`), enabled: id !== undefined, refetchInterval: 30000, retry: false, gcTime: 0 })
  const history = useQuery({ queryKey: ['trades', sessionKey, id, cursor], queryFn: () => request<History>(`/portfolios/${id}/trades?limit=25${cursor ? `&before=${cursor}` : ''}`), enabled: id !== undefined, retry: false, gcTime: 0 })
  async function act(action: () => Promise<unknown>, message: string) {
    setBusy(true); setError(''); setNotice('')
    try { await action(); setNotice(message); await Promise.all([list.refetch(), portfolio.refetch(), history.refetch()]) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Request failed') }
    finally { setBusy(false) }
  }
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const initial_cash = new FormData(event.currentTarget).get('cash')
    setBusy(true); setError('')
    try { await request('/portfolios', 'POST', { initial_cash }); await list.refetch() }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Request failed') }
    finally { setBusy(false) }
  }
  function order(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const fields = Object.fromEntries(new FormData(form))
    const fingerprint = JSON.stringify(fields)
    if (orderAttempt.current?.fingerprint !== fingerprint) orderAttempt.current = { fingerprint, id: crypto.randomUUID() }
    const body = { ...fields, client_order_id: orderAttempt.current.id } as unknown as PaperRequest
    const preview = (event.nativeEvent as SubmitEvent).submitter?.getAttribute('value') === 'preview'
    void act(async () => {
      await request(`/portfolios/${id}/orders${preview ? '/preview' : ''}`, 'POST', body)
      if (!preview) { orderAttempt.current = null; form.reset() }
    }, preview ? 'Risk check passed. Reserving the trade will check the current balances again.' : 'Paper trade reserved. Fill or cancel it below.')
  }
  function saveRisk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const values = Object.fromEntries(new FormData(event.currentTarget))
    void act(async () => {
      await request(`/portfolios/${id}/risk`, 'PUT', { ...values,
        max_open_positions: Number(values.max_open_positions), max_open_trades: Number(values.max_open_trades),
        stop_loss_pct: values.stop_loss_pct || null, take_profit_pct: values.take_profit_pct || null,
      }); await portfolio.refetch(); setRiskRevision(value => value + 1)
    }, 'Risk settings saved. Existing reservations keep their recorded thresholds.')
  }
  const p = portfolio.data
  return <>
    <div className="portfolio-toolbar"><h2>Portfolio overview</h2><button disabled={busy} onClick={() => { void list.refetch(); if (id) { void portfolio.refetch(); void history.refetch() } }}>Refresh</button></div>
    {(error || list.error || portfolio.error || history.error) && <p role="alert" className="error-banner">{error || list.error?.message || portfolio.error?.message || history.error?.message}</p>}
    {notice && <p role="status" className="success-banner">{notice}</p>}
    {list.isPending && <p role="status">Loading portfolio…</p>}
    {list.data?.length === 0 && <div className="market-panel portfolio-card"><h3>Create your paper portfolio</h3><p>Choose a one-time virtual starting balance. This is simulated cash, not a deposit.</p>
      <form className="portfolio-form" onSubmit={create}><label>Starting virtual USD<input name="cash" {...inputNumber} max="1000000000" defaultValue="10000" /></label><button className="primary-button" disabled={busy}>Create paper portfolio</button></form></div>}
    {id && portfolio.isPending && <p role="status">Loading balances…</p>}
    {p && <>
      {!p.valuation_complete && <p role="status" className="error-banner">Valuation incomplete: no fresh market price for {p.unpriced_symbols.join(', ')}. Total value, allocation and unrealized P&L are unavailable. Cash and realized P&L remain available.</p>}
      <div className="portfolio-metrics">{[
        ['Total value', p.total_value], ['Available cash', p.available_cash], ['Reserved cash', p.reserved_cash],
        ['Realized P&L', p.realized_pnl], ['Unrealized P&L', p.unrealized_pnl], ['Total P&L', p.total_pnl],
      ].map(([label, value]) => <div className="market-panel portfolio-card" key={label}><span>{label}</span><strong>{usd(value)}</strong></div>)}</div>
      <section className="market-panel"><div className="section-heading"><h3>Holdings & allocation</h3><span>Cash: {usd(p.cash_balance)} · {pct(p.cash_allocation_pct)}</span></div>
        <div className="market-table-wrap"><table className="market-table"><thead><tr><th>Asset</th><th>Quantity / available</th><th>Average cost</th><th>Market value</th><th>Unrealized P&L</th><th>Allocation</th></tr></thead>
          <tbody>{p.holdings.length ? p.holdings.map(h => <tr key={h.symbol}><td>{h.symbol}</td><td>{h.quantity} / {h.available_quantity}</td><td>{usd(h.average_cost)}</td><td title={h.price_as_of ? `Price at ${h.price_as_of}` : 'No fresh price'}>{usd(h.market_value)}</td><td>{usd(h.unrealized_pnl)}</td><td>{pct(h.allocation_pct)}</td></tr>) : <tr><td colSpan={6} className="table-state">No holdings yet. Reserve and fill a paper buy to begin.</td></tr>}</tbody></table></div>
      </section>
      <div className="portfolio-columns"><section className="market-panel portfolio-card"><h3>New paper trade</h3><p>Enter a simulation price in USD. Fills use this exact price and your fee, independently of live quotes.</p>
        <form className="portfolio-form" onSubmit={order}><fieldset disabled={busy}>
          <label>Asset symbol<input name="symbol" required pattern="[A-Za-z0-9]+" maxLength={20} placeholder="BTC" /></label>
          <label>Side<select name="side"><option value="buy">Buy</option><option value="sell">Sell</option></select></label>
          <label>Quantity<input name="quantity" {...inputNumber} /></label><label>Simulation price (USD)<input name="simulation_price" {...inputNumber} /></label>
          <label>Fee (USD)<input name="fee" type="number" step="0.00000001" min="0" required defaultValue="0" /></label>
          <div className="portfolio-toolbar"><button type="submit" value="preview">Check risk</button><button className="primary-button" type="submit" value="reserve">Reserve paper trade</button></div>
        </fieldset></form></section>
      <section className="market-panel portfolio-card"><h3>Risk settings</h3><p>Investment bounds include buy fees. Sells may exit below the minimum. Position limits include reserved buys; open trades are pending reservations.</p>
        <RiskForm key={`${id}-${riskRevision}`} settings={p.risk_settings} busy={busy} onSubmit={saveRisk} />
        <p className="muted">Stop-loss and take-profit are recorded for new buys. Automatic monitoring and execution arrive in Phase 7.</p>
      </section></div>
      <section className="market-panel"><div className="section-heading"><h3>Pending paper trades</h3><span>{p.pending_orders.length} open</span></div><div className="market-table-wrap"><table className="market-table"><thead><tr><th>Asset / side</th><th>Quantity</th><th>Simulation price</th><th>Fee</th><th>Stop / target</th><th>Actions</th></tr></thead><tbody>
        {p.pending_orders.length ? p.pending_orders.map(o => <tr key={o.order_id}><td>{o.symbol} · {o.side}</td><td>{o.quantity}</td><td>{usd(o.simulation_price)}</td><td>{usd(o.fee)}</td><td>{o.stop_loss_price === null ? '—' : usd(o.stop_loss_price)} / {o.take_profit_price === null ? '—' : usd(o.take_profit_price)}</td><td><div className="portfolio-toolbar"><button disabled={busy} onClick={() => void act(() => request(`/portfolios/${id}/orders/${o.order_id}/fill`, 'POST'), 'Paper fill recorded. Balances and history updated.')}>Fill paper trade</button><button disabled={busy} onClick={() => void act(() => request(`/portfolios/${id}/orders/${o.order_id}/cancel`, 'POST'), 'Reservation cancelled.')}>Cancel</button></div></td></tr>) : <tr><td colSpan={6} className="table-state">No pending trades.</td></tr>}
      </tbody></table></div></section>
      <section className="market-panel"><div className="section-heading"><h3>Trade history</h3><span>Paper fills · average-cost accounting</span></div><div className="market-table-wrap"><table className="market-table"><thead><tr><th>Time</th><th>Asset / side</th><th>Quantity</th><th>Price</th><th>Fee</th><th>Realized P&L</th></tr></thead><tbody>
        {history.isPending ? <tr><td colSpan={6}>Loading history…</td></tr> : history.data?.items.length ? history.data.items.map(t => <tr key={t.trade_id}><td>{new Date(t.created_at).toLocaleString()}</td><td>{t.symbol} · {t.side}</td><td>{t.quantity}</td><td>{usd(t.price)}</td><td>{usd(t.fee)}</td><td>{usd(t.realized_pnl)}</td></tr>) : <tr><td colSpan={6} className="table-state">No completed paper trades.</td></tr>}
      </tbody></table></div><div className="portfolio-toolbar portfolio-card"><button disabled={cursor === null || busy} onClick={() => setCursor(null)}>Latest trades</button><button disabled={!history.data?.next_cursor || busy} onClick={() => setCursor(history.data?.next_cursor ?? null)}>Older trades</button></div></section>
    </>}
  </>
}

function RiskForm({ settings, busy, onSubmit }: { settings: RiskSettings; busy: boolean; onSubmit: (e: FormEvent<HTMLFormElement>) => void }) {
  return <form className="portfolio-form" onSubmit={onSubmit}><fieldset disabled={busy}>
    <label>Minimum investment (USD)<input name="min_investment" {...inputNumber} defaultValue={settings.min_investment} /></label>
    <label>Maximum investment (USD)<input name="max_investment" {...inputNumber} defaultValue={settings.max_investment} /></label>
    <label>Maximum open positions<input name="max_open_positions" type="number" required min="1" max="100" defaultValue={settings.max_open_positions} /></label>
    <label>Maximum open trades<input name="max_open_trades" type="number" required min="1" max="100" defaultValue={settings.max_open_trades} /></label>
    <label>Stop-loss % (blank disables)<input name="stop_loss_pct" type="number" step="0.0001" min="0.0001" max="99.9999" defaultValue={settings.stop_loss_pct ?? ''} /></label>
    <label>Take-profit % (blank disables)<input name="take_profit_pct" type="number" step="0.0001" min="0.0001" max="1000" defaultValue={settings.take_profit_pct ?? ''} /></label>
    <button className="primary-button">Save risk settings</button>
  </fieldset></form>
}
