import { useState } from 'react'
import type { FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'

type Request = <T>(path: string, method?: string, body?: unknown) => Promise<T>
export interface Forecast {
  symbol: string; interval: string; quote_asset: string; model_version: string
  as_of: string; forecast_for: string; generated_at: string
  current_price: number; predicted_price: number; direction: 'up' | 'down' | 'neutral'
  up_probability: number; confidence: number; confidence_kind: string
  expected_return: number; estimated_risk: number; validation_error_p95: number
  drift?: { status: string }
}
interface Ranking { items: { forecast: Forecast; score: number }[]; unavailable: Record<string, string> }
interface ModelVersion { version: string; algorithm: string; trained_at: string; is_active: boolean }

// 1M is excluded: too few monthly candles exist to train a model (see docs/DEMO_WORKFLOW.md, Part B).
const INTERVALS = ['1h', '4h', '1d', '1w']
// Top-50 coins with a Binance USDT pair and enough history to train on all four intervals (docs/DEMO_WORKFLOW.md, Part B).
export const COINS = ['BTC', 'ETH', 'BNB', 'XRP', 'SOL', 'TRX', 'ZEC', 'DOGE', 'LINK', 'ADA', 'XLM', 'NEAR', 'BCH', 'LTC', 'AVAX', 'UNI', 'HBAR', 'AAVE', 'PAXG', 'USDC']
const ARROW = { up: '▲', down: '▼', neutral: '◆' }
const price = (value: number) => value.toLocaleString(undefined, { maximumFractionDigits: value < 1 ? 6 : 2 })
const pct = (value: number) => `${value >= 0 ? '+' : ''}${(value * 100).toFixed(2)}%`
const when = (value: string) => new Date(value).toLocaleString()
const tone = (direction: Forecast['direction']) => direction === 'up' ? 'positive' : direction === 'down' ? 'negative' : ''
const message = (cause: unknown) => cause instanceof Error ? cause.message : 'Prediction request failed'

export default function PredictionsDashboard({ request }: { request: Request }) {
  const [symbol, setSymbol] = useState('BTC')
  const [interval, setTimeframe] = useState('1d')
  const [rankSymbols, setRankSymbols] = useState('BTC, ETH, SOL, BNB, XRP')
  const [rankFor, setRankFor] = useState<{ symbols: string[]; interval: string } | null>(null)

  const forecast = useQuery({ queryKey: ['forecast', symbol, interval], queryFn: () => request<Forecast>(`/predictions/${encodeURIComponent(symbol)}?interval=${interval}`), retry: false, gcTime: 0 })
  const models = useQuery({ queryKey: ['forecast-models', symbol, interval], queryFn: () => request<ModelVersion[]>(`/predictions/models/${encodeURIComponent(symbol)}?interval=${interval}`), retry: false, gcTime: 0 })
  const ranking = useQuery({ queryKey: ['forecast-ranking', rankFor], queryFn: () => request<Ranking>('/predictions/opportunities', 'POST', rankFor), enabled: Boolean(rankFor), retry: false, gcTime: 0 })

  function choose(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void forecast.refetch(); void models.refetch()
  }
  function rank(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const symbols = [...new Set(rankSymbols.split(/[\s,]+/).map(s => s.trim().toUpperCase()).filter(Boolean))].slice(0, 20)
    if (symbols.length) setRankFor({ symbols, interval })
  }

  const f = forecast.data
  return <section className="portfolio-shell">
    <div className="portfolio-toolbar"><h2>AI predictions</h2><span className="live-pill">Educational forecast · not financial advice</span><button disabled={forecast.isFetching} onClick={() => { void forecast.refetch(); void models.refetch() }}>Refresh forecast</button></div>
    <p className="subtitle">Next-candle forecasts from the active trained model (Random Forest, XGBoost and LSTM). Only symbols and intervals with an active trained model are available. Confidence is uncalibrated.</p>

    <div className="portfolio-columns">
      <section className="market-panel portfolio-card"><h3>Forecast</h3>
        <form className="portfolio-form" onSubmit={choose}>
          <label>Symbol<select value={symbol} onChange={e => setSymbol(e.target.value)}>{COINS.map(c => <option key={c}>{c}</option>)}</select></label>
          <label>Interval<select value={interval} onChange={e => setTimeframe(e.target.value)}>{INTERVALS.map(v => <option key={v}>{v}</option>)}</select></label>
          <button className="primary-button" disabled={forecast.isFetching}>{forecast.isFetching ? 'Forecasting…' : 'Get forecast'}</button>
        </form>
      </section>

      <section className="market-panel portfolio-card" aria-live="polite">
        <h3>{symbol}/{f?.quote_asset ?? 'USDT'} · {interval}</h3>
        {forecast.isPending && <p role="status">Loading forecast…</p>}
        {forecast.isError && <p role="alert" className="error-banner">{message(forecast.error)}. Train and activate a model for {symbol} {interval} first.</p>}
        {f && <>
          <p className={`price-line ${tone(f.direction)}`}>{ARROW[f.direction]} {f.direction.toUpperCase()}</p>
          <div className="portfolio-metrics">
            <div><span>Current price</span><strong>{price(f.current_price)}</strong></div>
            <div><span>Predicted price</span><strong className={tone(f.direction)}>{price(f.predicted_price)}</strong></div>
            <div><span>Expected return</span><strong className={f.expected_return >= 0 ? 'positive' : 'negative'}>{pct(f.expected_return)}</strong></div>
            <div><span>Confidence</span><strong>{(f.confidence * 100).toFixed(1)}%</strong></div>
            <div><span>Up probability</span><strong>{(f.up_probability * 100).toFixed(1)}%</strong></div>
            <div><span>Estimated risk</span><strong>{(f.estimated_risk * 100).toFixed(2)}%</strong></div>
          </div>
          <dl>
            <dt>Forecast for</dt><dd>{when(f.forecast_for)} (data as of {when(f.as_of)})</dd>
            <dt>Typical error (95th percentile)</dt><dd>±{(f.validation_error_p95 * 100).toFixed(2)}%</dd>
            <dt>Feature drift</dt><dd>{f.drift?.status ?? 'unknown'}</dd>
            <dt>Model version</dt><dd>{f.model_version}</dd>
          </dl>
        </>}
      </section>
    </div>

    <section className="market-panel portfolio-card"><h3>Opportunity ranking</h3>
      <form className="portfolio-form" onSubmit={rank}>
        <label>Symbols to compare (up to 20, comma separated)<input value={rankSymbols} onChange={e => setRankSymbols(e.target.value)} required /></label>
        <button className="primary-button" disabled={ranking.isFetching}>{ranking.isFetching ? 'Ranking…' : `Rank on ${interval}`}</button>
      </form>
      {ranking.isError && <p role="alert" className="error-banner">{message(ranking.error)}</p>}
      {ranking.data && <>
        <div className="market-table-wrap"><table className="market-table">
          <thead><tr><th>#</th><th>Symbol</th><th>Direction</th><th>Expected return</th><th>Confidence</th><th>Risk</th><th>Score</th></tr></thead>
          <tbody>
            {ranking.data.items.length === 0 && <tr><td colSpan={7} className="table-state">No symbol has an active model for {rankFor?.interval}.</td></tr>}
            {ranking.data.items.map((item, index) => <tr key={item.forecast.symbol}>
              <td>{index + 1}</td><td>{item.forecast.symbol}</td>
              <td className={tone(item.forecast.direction)}>{ARROW[item.forecast.direction]} {item.forecast.direction}</td>
              <td className={item.forecast.expected_return >= 0 ? 'positive' : 'negative'}>{pct(item.forecast.expected_return)}</td>
              <td>{(item.forecast.confidence * 100).toFixed(1)}%</td>
              <td>{(item.forecast.estimated_risk * 100).toFixed(2)}%</td>
              <td>{item.score.toFixed(3)}</td>
            </tr>)}
          </tbody>
        </table></div>
        {Object.keys(ranking.data.unavailable).length > 0 && <p className="muted">No active model: {Object.keys(ranking.data.unavailable).join(', ')}</p>}
      </>}
    </section>

    <section className="market-panel portfolio-card"><h3>Model versions · {symbol} {interval}</h3>
      {models.isError && <p role="alert" className="error-banner">{message(models.error)}</p>}
      {models.data && models.data.length === 0 && <p className="muted">No trained versions yet.</p>}
      {models.data && models.data.length > 0 && <div className="market-table-wrap"><table className="market-table">
        <thead><tr><th>Version</th><th>Algorithm</th><th>Trained</th><th>Status</th></tr></thead>
        <tbody>{models.data.map(m => <tr key={m.version}><td>{m.version}</td><td>{m.algorithm}</td><td>{when(m.trained_at)}</td><td className={m.is_active ? 'positive' : ''}>{m.is_active ? 'Active' : 'Inactive'}</td></tr>)}</tbody>
      </table></div>}
    </section>
  </section>
}
