import MarketDashboard from './components/MarketDashboard'

export default function App() {
  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Market Data · Phase 3</p>
          <h1>AI Crypto Trading Platform</h1>
          <p className="subtitle">Live market ranking, historical candles, and technical indicators for research and education.</p>
        </div>
        <div className="education-badge">Educational platform · Not financial advice</div>
      </header>
      <MarketDashboard />
    </main>
  )
}
