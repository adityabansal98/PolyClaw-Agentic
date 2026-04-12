import { useState } from 'react'

import './App.css'
import { AuthScreen } from './components/AuthScreen'
import { StatusPill } from './components/StatusPill'
import type { NavSection } from './lib/types'
import { usePrototypeDashboard } from './hooks/usePrototypeDashboard'
import { OpportunitiesPage } from './pages/OpportunitiesPage'
import { PositionsPage } from './pages/PositionsPage'

function App() {
  const [activeSection, setActiveSection] = useState<NavSection>('opportunities')
  const dashboard = usePrototypeDashboard()

  if (!dashboard.sessionUser) {
    return (
      <AuthScreen
        error={dashboard.authError}
        onSignIn={dashboard.signIn}
        onCreateAccount={dashboard.createAccount}
      />
    )
  }

  return (
    <div className="app-shell">
      <aside className="sidebar sidebar--slim">
        <div className="brand brand--slim">
          <p className="brand__name">PolyClaw</p>
          <p className="brand__sub muted">Trading Desk</p>
        </div>

        <nav className="nav-stack" aria-label="Primary">
          {([
            { id: 'opportunities' as NavSection, label: 'Opportunities', badge: dashboard.scoredOpportunities.length || null },
            { id: 'positions' as NavSection, label: 'Positions', badge: dashboard.positions.length || null },
          ]).map((item) => (
            <button
              key={item.id}
              className={`nav-button ${activeSection === item.id ? 'is-active' : ''}`}
              type="button"
              onClick={() => setActiveSection(item.id)}
            >
              <span>{item.label}</span>
              {item.badge ? <span className="nav-button__badge">{item.badge}</span> : null}
            </button>
          ))}
        </nav>

        <div className="sidebar__footer">
          <StatusPill tone="info">Live Polymarket feed</StatusPill>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar topbar--slim">
          <span className="topbar__app-name">PolyClaw</span>
          <div className="topbar__actions">
            <StatusPill tone={dashboard.killSwitchEnabled ? 'critical' : 'positive'}>
              {dashboard.killSwitchEnabled ? 'Kill switch ON' : 'Paper ready'}
            </StatusPill>
            <div className="user-chip">
              <strong>{dashboard.sessionUser.name}</strong>
            </div>
            <button className="button button--ghost" type="button" onClick={dashboard.signOut}>
              Sign out
            </button>
          </div>
        </header>

        <main className="workspace__content">
          {activeSection === 'opportunities' ? (
            <OpportunitiesPage
              scoredOpportunities={dashboard.scoredOpportunities}
              scoredLoading={dashboard.scoredLoading}
              paperActionBlockedReason={dashboard.paperActionBlockedReason}
              onPlaceBet={dashboard.placeScoredBet}
            />
          ) : (
            <PositionsPage
              positions={dashboard.positions}
              portfolioSummary={dashboard.paperSummary}
              sessionUser={dashboard.sessionUser}
              actionBlockedReason={dashboard.paperActionBlockedReason}
              pausedCategories={dashboard.pausedCategories}
              onClosePosition={dashboard.closePosition}
              onResizePosition={dashboard.resizePosition}
              onMarkReview={dashboard.markPositionReview}
              onPauseCategory={dashboard.pauseCategory}
              onAddNote={dashboard.addPositionNote}
            />
          )}
        </main>
      </div>
    </div>
  )
}

export default App
