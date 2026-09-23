import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../api/portfolio'

type Request = <T>(path: string, method?: string, body?: unknown) => Promise<T>
type User = { user_id: number; username: string; email: string; role: string; is_active: boolean; is_email_verified: boolean; totp_enabled: boolean }
type Model = { model_id: number; algorithm: string; model_version: string; symbol: string | null; timeframe: string | null; is_active: boolean; trained_at: string; last_prediction_at: string | null; metrics: unknown; backtest: unknown }
type Page<T> = { items: T[]; next_cursor: number | null }
type Overview = { observed_at: string; users_total: number; users_active: number; bots_running: number; bots_error: number; trading_worker_status: string; trading_worker_seen_at: string | null; postgres_status: string; sandbox_orders_unresolved: number; email_pending: number; email_failed: number }
type Operations = { observed_at: string; bots: { bot_id: string; symbol: string; state: string; failures: number; last_result: string | null; last_tick_at: string | null }[]; exchanges: { exchange: string; sandbox: boolean; connections: number; status: string; last_failure_at: string | null }[] }
const time = (value: string | null) => value ? new Date(value).toLocaleString() : 'Not recorded'

export default function AdminDashboard({ request }: { request: Request }) {
  const [key] = useState(() => crypto.randomUUID())
  const [usersBefore, setUsersBefore] = useState<number | null>(null)
  const [modelsBefore, setModelsBefore] = useState<number | null>(null)
  const cache = useQueryClient()
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [health, setHealth] = useState<{ items: { name: string; status: string; latency_ms?: number; observed_at: string }[]; scope: string } | null>(null)
  const [checks, setChecks] = useState<Record<number, string>>({})
  const [auditBefore, setAuditBefore] = useState<number | null>(null)
  async function action(operation: () => Promise<unknown>) {
    setBusy(true); setActionError('')
    try { await operation(); await cache.invalidateQueries({ predicate: q => q.queryKey[1] === key }) }
    catch (error) { setActionError(error instanceof Error ? error.message : 'Request failed') }
    finally { setBusy(false) }
  }
  const common = { retry: false as const, gcTime: 0, refetchInterval: 15000 }
  const overview = useQuery({ queryKey: ['admin-overview', key], queryFn: () => request<Overview>('/admin/overview'), ...common })
  const users = useQuery({ queryKey: ['admin-users', key, usersBefore], queryFn: () => request<Page<User>>(`/admin/users${usersBefore ? `?before=${usersBefore}` : ''}`), ...common })
  const models = useQuery({ queryKey: ['admin-models', key, modelsBefore], queryFn: () => request<Page<Model>>(`/admin/models${modelsBefore ? `?before=${modelsBefore}` : ''}`), ...common })
  const operations = useQuery({ queryKey: ['admin-operations', key], queryFn: () => request<Operations>('/admin/operations'), ...common })
  const audit = useQuery({ queryKey: ['admin-audit', key, auditBefore], queryFn: () => request<Page<{ audit_id: number; actor_id: number; target_id: number; action: string; details: unknown; created_at: string }>>(`/admin/audit${auditBefore ? `?before=${auditBefore}` : ''}`), ...common })
  const errors = [overview.error, users.error, models.error, operations.error, audit.error].filter(Boolean)
  if (errors.some(error => error instanceof ApiError && (error.status === 401 || error.status === 403))) return <p role="alert">Administrator access is no longer available. Refresh your session.</p>
  return <section className="market-panel">
    <h2>Administration</h2>
    <p>Account management and operational status. Updates every 15 seconds.</p>
    {actionError && <p role="alert" className="error-banner">{actionError}</p>}
    {errors.length > 0 && <p role="alert" className="error-banner">{errors.map(String).join(' · ')}</p>}
    {overview.isPending && <p>Loading operational overview…</p>}
    {overview.data && <>
      <p>Observed {time(overview.data.observed_at)} · PostgreSQL: {overview.data.postgres_status}</p>
      <p>Active users: {overview.data.users_active} / {overview.data.users_total} · Running bots: {overview.data.bots_running} · Bots in error: {overview.data.bots_error}</p>
      <p>Trading worker: {overview.data.trading_worker_status} · Last heartbeat: {time(overview.data.trading_worker_seen_at)}</p>
      <p>Unresolved sandbox orders: {overview.data.sandbox_orders_unresolved} · Pending emails: {overview.data.email_pending} · Failed emails: {overview.data.email_failed}</p>
    </>}
    <h3>Live health checks</h3>
    <button disabled={busy} onClick={() => void action(async () => setHealth(await request('/admin/health/check', 'POST')))}>Check storage and providers</button>
    {health && <><p>{health.scope}</p>{health.items.map(item => <p key={item.name}>{item.name}: {item.status} · {item.latency_ms ?? '—'} ms · {time(item.observed_at)}</p>)}</>}
    <h3>Users</h3><p>Stop active bots and reconcile pending orders before deactivating an account. Your own account cannot be demoted or deactivated.</p>
    {users.isPending && <p>Loading users…</p>}
    <div className="table-wrap"><table><thead><tr><th>User</th><th>Email</th><th>Role</th><th>Active</th><th>Verified</th><th>2FA</th><th>Manage</th></tr></thead><tbody>{users.data?.items.map(u => <tr key={u.user_id}><td>{u.username}</td><td>{u.email}</td><td>{u.role}</td><td>{String(u.is_active)}</td><td>{String(u.is_email_verified)}</td><td>{String(u.totp_enabled)}</td><td>
      <button disabled={busy} onClick={() => { if (window.confirm(`${u.is_active ? 'Deactivate' : 'Activate'} ${u.username}?`)) void action(() => request(`/admin/users/${u.user_id}`, 'PUT', { role: u.role, is_active: !u.is_active })) }}>{u.is_active ? 'Deactivate' : 'Activate'}</button>
      <button disabled={busy} onClick={() => { const role = u.role === 'admin' ? 'trader' : 'admin'; if (window.confirm(`Change ${u.username} to ${role}?`)) void action(() => request(`/admin/users/${u.user_id}`, 'PUT', { role, is_active: u.is_active })) }}>Make {u.role === 'admin' ? 'trader' : 'admin'}</button>
    </td></tr>)}</tbody></table></div>
    <button disabled={usersBefore === null} onClick={() => setUsersBefore(null)}>Newest users</button><button disabled={!users.data?.next_cursor} onClick={() => setUsersBefore(users.data?.next_cursor ?? null)}>Older users</button>
    <h3>Model registry</h3><p>Recorded training metrics and forecast timestamps. Use Check prediction to validate the active model and record a forecast; no trade is placed.</p>
    {models.isPending && <p>Loading models…</p>}
    {models.data?.items.length === 0 && <p>No registered models.</p>}
    {models.data?.items.map(m => <details key={m.model_id}><summary>{m.symbol ?? 'Legacy'} · {m.timeframe ?? '—'} · {m.model_version} · {m.is_active ? 'Active' : 'Inactive'}</summary><p>{m.algorithm} · Trained {time(m.trained_at)} · Last forecast {time(m.last_prediction_at)}</p>{m.is_active && <button disabled={busy} onClick={() => void action(async () => { const result = await request<{ status: string; observed_at: string }>(`/admin/models/${m.model_id}/check`, 'POST'); setChecks(current => ({ ...current, [m.model_id]: `${result.status} · ${time(result.observed_at)}` })) })}>Check prediction</button>}{checks[m.model_id] && <p>{checks[m.model_id]}</p>}<h4>Metrics</h4><pre>{JSON.stringify(m.metrics, null, 2)}</pre><h4>Backtest</h4><pre>{JSON.stringify(m.backtest, null, 2)}</pre></details>)}
    <button disabled={modelsBefore === null} onClick={() => setModelsBefore(null)}>Newest models</button><button disabled={!models.data?.next_cursor} onClick={() => setModelsBefore(models.data?.next_cursor ?? null)}>Older models</button>
    <h3>Exchange observations</h3><p>Failures recorded in the last 24 hours. Unknown means no recent failure was recorded, not that a provider is healthy.</p>
    {operations.isPending && <p>Loading operations…</p>}
    {operations.data?.exchanges.map(e => <p key={`${e.exchange}-${e.sandbox}`}>{e.exchange} · {e.sandbox ? 'Sandbox' : 'Production read-only'} · Connections: {e.connections} · {e.status} · Last failure: {time(e.last_failure_at)}</p>)}
    <h3>Bots requiring attention</h3><p>Up to 50 recent bots with recorded failures.</p>
    {operations.data?.bots.length === 0 && <p>No bots with recorded failures.</p>}
    {operations.data?.bots.map(b => <p key={b.bot_id}>{b.symbol} · {b.bot_id} · {b.state} · Failures: {b.failures} · Result: {b.last_result ?? '—'} · {time(b.last_tick_at)}</p>)}
    <h3>Administration audit</h3>
    {audit.data?.items.length === 0 && <p>No recorded changes.</p>}
    {audit.data?.items.map(item => <details key={item.audit_id}><summary>{time(item.created_at)} · Actor {item.actor_id} · User {item.target_id} · {item.action}</summary><pre>{JSON.stringify(item.details,null,2)}</pre></details>)}
    <button disabled={auditBefore === null} onClick={() => setAuditBefore(null)}>Newest changes</button><button disabled={!audit.data?.next_cursor} onClick={() => setAuditBefore(audit.data?.next_cursor ?? null)}>Older changes</button>
  </section>
}
