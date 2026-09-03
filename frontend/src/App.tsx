const modules = [
  'Market Data',
  'AI Prediction',
  'Portfolio & Risk',
  'Automated Trading',
  'Alerts & Reporting',
]

export default function App() {
  return (
    <main className="page-shell">
      <section className="hero-card">
        <p className="eyebrow">Foundation</p>
        <h1>AI Crypto Trading Platform</h1>
        <p className="subtitle">
          Project foundation is ready. Product features will be delivered on dedicated feature branches.
        </p>
        <div className="module-grid">
          {modules.map((module) => (
            <div className="module-card" key={module}>
              <span className="status-dot" aria-hidden="true" />
              <span>{module}</span>
            </div>
          ))}
        </div>
      </section>
    </main>
  )
}
