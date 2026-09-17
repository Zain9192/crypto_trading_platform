import { useState } from 'react'
import type { FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNotificationSocket } from '../hooks/useNotificationSocket'
import { fetchTopAssets } from '../api/market'

type Request = <T>(path: string, method?: string, body?: unknown) => Promise<T>
type Notice = { notification_id: number; kind: string; created_at: string; read_at: string | null; payload: Record<string, string> }
type Inbox = { items: Notice[]; unread_count: number; next_cursor: number | null }
type Alert = { alert_id: number; asset_key: string; direction: string; threshold: string; triggered_at: string | null }

export default function NotificationsDashboard({ request, getToken }: { request: Request; getToken: () => Promise<string> }) {
  const [key] = useState(() => crypto.randomUUID())
  const [cursor, setCursor] = useState<number | null>(null)
  const [unread, setUnread] = useState(false)
  const today = new Date().toISOString().slice(0, 10)
  const [start, setStart] = useState(today.slice(0, 7) + '-01')
  const [end, setEnd] = useState(today)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const cache = useQueryClient()
  const connected = useNotificationSocket(getToken, () => {
    void cache.invalidateQueries({ queryKey: ['notifications', key] })
    void cache.invalidateQueries({ queryKey: ['price-alerts', key] })
  })
  const common = { retry: false as const, gcTime: 0 }
  const inbox = useQuery({ queryKey: ['notifications', key, cursor, unread], queryFn: () => request<Inbox>(`/notifications?unread_only=${unread}${cursor ? `&before=${cursor}` : ''}`), refetchInterval: 10000, ...common })
  const alerts = useQuery({ queryKey: ['price-alerts', key], queryFn: () => request<Alert[]>('/notifications/price-alerts'), refetchInterval: 10000, ...common })
  const preferences = useQuery({ queryKey: ['notification-preferences', key], queryFn: () => request<{ email_enabled: boolean; delivery_configured: boolean; pending: number; failed: number }>('/notifications/preferences'), refetchInterval: 10000, ...common })
  const assets = useQuery({ queryKey: ['alert-assets', key], queryFn: () => fetchTopAssets(), ...common })
  async function action(operation: () => Promise<unknown>) {
    setBusy(true); setError('')
    try {
      await operation()
      await Promise.all([cache.invalidateQueries({ queryKey: ['notifications', key] }), cache.invalidateQueries({ queryKey: ['price-alerts', key] }), cache.invalidateQueries({ queryKey: ['notification-preferences', key] })])
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Request failed') }
    finally { setBusy(false) }
  }
  async function download(format: 'csv' | 'pdf') {
    await action(async () => {
      const result = await request<{ filename: string; content_type: string; content_base64: string }>(`/notifications/reports/trades?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&format=${format}`)
      const bytes = Uint8Array.from(atob(result.content_base64), character => character.charCodeAt(0))
      const url = URL.createObjectURL(new Blob([bytes], { type: result.content_type }))
      const link = document.createElement('a')
      link.href = url; link.download = result.filename; document.body.appendChild(link); link.click(); link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    })
  }
  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    void action(async () => {
      await request('/notifications/price-alerts', 'POST', { asset_key: data.get('asset'), direction: data.get('direction'), threshold: data.get('threshold') })
      form.reset()
    })
  }
  function message(n: Notice) {
    const p = n.payload
    if (n.kind === 'price_alert') return `${p.symbol.toUpperCase()} reached ${p.price} USD (${p.direction} ${p.threshold} USD).`
    if (n.kind === 'trade_executed') return `${p.mode} ${p.side}: ${p.quantity} ${p.symbol} at ${p.price} ${p.quote_currency}. Fee: ${p.fee} ${p.fee_currency ?? p.quote_currency}.`
    if (n.kind === 'stop_loss' || n.kind === 'take_profit') return `${n.kind === 'stop_loss' ? 'Stop loss' : 'Take profit'} executed: ${p.quantity} ${p.symbol} at ${p.price} ${p.quote_currency} (${p.mode}).`
    if (n.kind === 'bot_failure' || n.kind === 'exchange_failure') return `${p.symbol}: ${p.message}`
    return n.kind.replaceAll('_', ' ')
  }
  return <section className="market-panel">
    <h2>Notifications & price alerts</h2>
    {(error || inbox.error || alerts.error || assets.error || preferences.error) && <p role="alert" className="error-banner">{error || String(inbox.error ?? alerts.error ?? assets.error ?? preferences.error)}</p>}
    <h3>Email notifications</h3>
    <label><input type="checkbox" disabled={busy || !preferences.data} checked={preferences.data?.email_enabled ?? false}
      onChange={e => void action(() => request('/notifications/preferences', 'PUT', { email_enabled: e.target.checked }))} /> Send new notifications to my verified account email</label>
    {preferences.data && <p>{preferences.data.delivery_configured ? 'Email delivery configured.' : 'Email delivery awaits provider configuration.'} Pending: {preferences.data.pending} · Failed after retries: {preferences.data.failed}. Provider timeouts can cause duplicate emails. Disabling stops queued delivery; a message already being sent may still arrive.</p>}
    <h3>Trading reports</h3>
    <p>Export paper trades and sandbox fills, including fees. Dates use UTC; choose up to 367 days and 5,000 fills per export.</p>
    <div className="portfolio-form">
      <label>From<input type="date" value={start} onChange={e => setStart(e.target.value)} /></label>
      <label>Through<input type="date" value={end} onChange={e => setEnd(e.target.value)} /></label>
      <button disabled={busy || !start || !end || start > end} onClick={() => void download('csv')}>Download CSV</button>
      <button disabled={busy || !start || !end || start > end} onClick={() => void download('pdf')}>Download PDF</button>
    </div>
    <h3>Create a price alert</h3>
    <p>Alerts fire once when a fresh USD quote is at or beyond your threshold. Monitoring follows the market refresh cycle and covers assets in the current top 50. An asset outside that list waits until it returns.</p>
    <form className="portfolio-form" onSubmit={create}>
      <label>Asset<select name="asset" required><option value="">Select an asset</option>{assets.data?.items.map(a => <option key={a.id} value={a.id}>{a.name} ({a.symbol})</option>)}</select></label>
      <label>Condition<select name="direction"><option value="above">At or above</option><option value="below">At or below</option></select></label>
      <label>Price in USD<input name="threshold" type="number" min="0.00000001" step="0.00000001" required /></label>
      <button disabled={busy || !assets.data}>Create alert</button>
    </form>
    <h3>Your price alerts</h3>
    {alerts.isPending && <p>Loading alerts…</p>}
    {alerts.data?.length === 0 && <p>No price alerts yet.</p>}
    <ul>{alerts.data?.map(a => <li key={a.alert_id}>{a.asset_key}: {a.direction} {a.threshold} USD · {a.triggered_at ? `Triggered ${new Date(a.triggered_at).toLocaleString()}` : 'Waiting'} <button disabled={busy} onClick={() => void action(() => request(`/notifications/price-alerts/${a.alert_id}`, 'DELETE'))}>Remove</button></li>)}</ul>
    <h3>Inbox · {inbox.data?.unread_count ?? '…'} unread</h3>
    <label><input type="checkbox" checked={unread} onChange={e => { setUnread(e.target.checked); setCursor(null) }} /> Unread only</label>
    <p>{connected ? 'Live updates connected.' : 'Reconnecting to live updates; checking every 10 seconds.'} Paper trades and individual sandbox fills appear here.</p>
    {inbox.isPending && <p>Loading notifications…</p>}
    {inbox.data?.items.length === 0 && <p>No notifications on this page.</p>}
    <ul>{inbox.data?.items.map(n => <li key={n.notification_id}>
      <p>{message(n)}</p><time dateTime={n.created_at}>{new Date(n.created_at).toLocaleString()}</time>
      {n.read_at ? <span> · Read</span> : <button disabled={busy} onClick={() => void action(() => request(`/notifications/${n.notification_id}/read`, 'POST'))}>Mark read</button>}
    </li>)}</ul>
    <div className="portfolio-toolbar"><button disabled={cursor === null} onClick={() => setCursor(null)}>Newest</button><button disabled={!inbox.data?.next_cursor} onClick={() => setCursor(inbox.data?.next_cursor ?? null)}>Older</button></div>
  </section>
}
