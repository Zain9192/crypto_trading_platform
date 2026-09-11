import { useState } from 'react'
import PortfolioAccess from './components/PortfolioAccess'
import MarketDashboard from './components/MarketDashboard'

export default function App() {
  const [tab, setTab] = useState<'market' | 'portfolio'>('market')
  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Market, portfolio & risk · Phase 5</p>
          <h1>AI Crypto Trading Platform</h1>
          <p className="subtitle">Explore market data, practice portfolio management, and test risk controls.</p>
        </div>
        <div className="education-badge">Educational platform · Not financial advice</div>
      </header>
      <nav className="app-tabs" aria-label="Dashboard sections">
        <button aria-pressed={tab === 'market'} onClick={() => setTab('market')}>Market data</button>
        <button aria-pressed={tab === 'portfolio'} onClick={() => setTab('portfolio')}>Portfolio & risk</button>
      </nav>
      <div hidden={tab !== 'market'}><MarketDashboard /></div>
      <div hidden={tab !== 'portfolio'}><PortfolioAccess /></div>
    </main>
  )
}
