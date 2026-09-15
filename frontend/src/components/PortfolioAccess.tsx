import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api, ApiError } from '../api/portfolio'
import type { Tokens } from '../api/portfolio'
import PortfolioDashboard from './PortfolioDashboard'
import ExchangeDashboard from './ExchangeDashboard'

export default function PortfolioAccess() {
  // Tokens live only in memory; reloading requires sign-in. No browser storage.
  const session = useRef<Tokens | null>(null)
  const refreshing = useRef<Promise<Tokens> | null>(null)
  const [signedIn, setSignedIn] = useState(false)
  const [section, setSection] = useState<'portfolio' | 'exchanges'>('portfolio')
  const [mode, setMode] = useState<'login' | 'register' | 'verify'>('login')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [verification, setVerification] = useState('')

  async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
    const current = session.current
    if (!current) throw new Error('Please sign in')
    try { return await api<T>(path, current.access_token, method, body) }
    catch (cause) {
      if (!(cause instanceof ApiError) || cause.status !== 401) throw cause
      try {
        // Concurrent requests share refresh-token rotation.
        if (session.current === current) {
          refreshing.current ??= api<Tokens>('/auth/refresh', undefined, 'POST', { refresh_token: current.refresh_token })
          const renewed = await refreshing.current
          if (!session.current) throw new Error('Signed out')
          session.current = renewed
        }
      } catch (refreshError) {
        session.current = null; setSignedIn(false); setError('Session expired. Please sign in again.')
        throw refreshError
      } finally { refreshing.current = null }
      // A business rejection after a successful refresh must not destroy the session.
      return api<T>(path, session.current?.access_token, method, body)
    }
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('')
    const form = new FormData(event.currentTarget)
    try {
      if (mode === 'login') {
        session.current = await api<Tokens>('/auth/login', undefined, 'POST', {
          email: form.get('email'), password: form.get('password'), totp_code: form.get('totp') || null,
        })
        setSignedIn(true)
      } else if (mode === 'register') {
        const result = await api<{ verification_token?: string }>('/auth/register', undefined, 'POST', {
          username: form.get('username'), email: form.get('email'), password: form.get('password'),
        })
        setVerification(result.verification_token ?? ''); setMode('verify')
        setNotice(result.verification_token ? 'Development account created. Confirm verification below.' : 'Account created. Enter your verification token. Contact the operator if email delivery is not configured.')
      } else {
        await api('/auth/verify-email', undefined, 'POST', { token: verification })
        setVerification(''); setMode('login'); setNotice('Email verified. You can now sign in.')
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Request failed') }
    finally { setBusy(false) }
  }
  async function logout() {
    setBusy(true); setError('')
    try {
      if (refreshing.current) session.current = await refreshing.current
      if (session.current) await api('/auth/logout', undefined, 'POST', { refresh_token: session.current.refresh_token })
      session.current = null; setSignedIn(false)
    } catch { setError('Sign-out could not be confirmed. Please retry.'); }
    finally { setBusy(false) }
  }
  if (signedIn) return <section className="portfolio-shell">
    <div className="portfolio-toolbar"><span className="live-pill">Account workspace</span><button disabled={busy} onClick={logout}>Sign out</button></div>
    {error && <p role="alert" className="error-banner">{error}</p>}
    <nav className="portfolio-toolbar" aria-label="Account sections">
      <button aria-pressed={section === 'portfolio'} onClick={() => setSection('portfolio')}>Paper portfolio</button>
      <button aria-pressed={section === 'exchanges'} onClick={() => setSection('exchanges')}>Exchange connections</button>
    </nav>
    {section === 'portfolio' ? <PortfolioDashboard request={request} /> : <ExchangeDashboard request={request} />}
  </section>
  return <section className="portfolio-shell market-panel auth-panel">
    <p className="eyebrow">Portfolio & risk</p><h2>{mode === 'login' ? 'Sign in to your portfolio' : mode === 'register' ? 'Create an account' : 'Verify your email'}</h2>
    <p className="subtitle">Practice with virtual USD, review holdings and P&L, and test risk limits. No real funds or exchange orders.</p>
    <form onSubmit={submit} className="portfolio-form">
      {mode === 'register' && <label>Username<input name="username" required minLength={3} autoComplete="username" /></label>}
      {mode !== 'verify' ? <>
        <label>Email<input name="email" type="email" required autoComplete="email" /></label>
        <label>Password<input name="password" type="password" required minLength={mode === 'register' ? 8 : 1} autoComplete={mode === 'register' ? 'new-password' : 'current-password'} /></label>
        {mode === 'login' && <label>2FA code (if enabled)<input name="totp" inputMode="numeric" pattern="[0-9]{6}" autoComplete="one-time-code" /></label>}
      </> : <label>Verification token<input value={verification} onChange={e => setVerification(e.target.value)} required minLength={20} autoComplete="off" /></label>}
      <button className="primary-button" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : mode === 'register' ? 'Register' : 'Verify email'}</button>
    </form>
    {error && <p role="alert" className="error-banner">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    <div className="portfolio-toolbar">{(['login', 'register', 'verify'] as const).filter(item => item !== mode).map(item =>
      <button key={item} disabled={busy} onClick={() => { setMode(item); setError(''); setNotice('') }}>{item === 'login' ? 'Back to sign in' : item === 'register' ? 'Create account' : 'Verify email'}</button>)}</div>
  </section>
}
