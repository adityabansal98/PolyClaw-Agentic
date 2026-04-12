import { useState } from 'react'

import './App.css'
import { AuthScreen } from './components/AuthScreen'
import { StatusPill } from './components/StatusPill'
import { formatRelativeTime } from './lib/format'
import type { NavSection } from './lib/types'
import { usePrototypeDashboard } from './hooks/usePrototypeDashboard'
import { OperationsPage } from './pages/OperationsPage'
import { OpportunitiesPage } from './pages/OpportunitiesPage'
import { OverviewPage } from './pages/OverviewPage'
import { PaperTradingPage } from './pages/PaperTradingPage'
import { PositionsPage } from './pages/PositionsPage'

const navItems: Array<{ id: NavSection; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'opportunities', label: 'Opportunities' },
  { id: 'positions', label: 'Positions' },
  { id: 'paper', label: 'Paper Trading' },
  { id: 'operations', label: 'Operations' },
]

function App() {
  const [activeSection, setActiveSection] = useState<NavSection>('overview')
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

  const paperExecutionHealthy = !dashboard.paperActionBlockedReason
  const opportunityCount = dashboard.opportunities.filter((opportunity) => opportunity.currentStage === 'new').length
  const paperCount = dashboard.paperOpportunities.length
  const positionCount = dashboard.positions.length

  let page = (
    <OverviewPage
      liveSummary={dashboard.liveSummary}
      paperSummary={dashboard.paperSummary}
      opportunities={dashboard.topOpportunities}
      positions={dashboard.positions}
      alerts={dashboard.alerts}
      services={dashboard.services}
      lastRefreshAt={dashboard.lastRefreshAt}
      liveHoldingsAvailable={dashboard.liveHoldingsAvailable}
      freshness={dashboard.freshness}
      onNavigate={setActiveSection}
    />
  )

  if (activeSection === 'opportunities') {
    page = (
      <OpportunitiesPage
        opportunities={dashboard.opportunities}
        opportunityDetails={dashboard.opportunityDetails}
        orderbooks={dashboard.orderbooks}
        sessionUser={dashboard.sessionUser}
        paperActionBlockedReason={dashboard.paperActionBlockedReason}
        liveActionBlockedReason={dashboard.liveActionBlockedReason}
        pausedCategories={dashboard.pausedCategories}
        detailRefreshMs={dashboard.detailRefreshMs}
        paperExecutionAvailable={dashboard.paperExecutionAvailable}
        liveExecutionAvailable={dashboard.liveExecutionAvailable}
        onApproveLive={dashboard.approveOpportunity}
        onSendToPaper={dashboard.sendToPaper}
        onReject={dashboard.rejectOpportunity}
        onAddNote={dashboard.addOpportunityNote}
        onAddLink={dashboard.addOpportunityLink}
        onAddFile={dashboard.addOpportunityFile}
        onLoadDetail={dashboard.loadOpportunityDetail}
        onLoadOrderbook={dashboard.loadOrderbook}
      />
    )
  }

  if (activeSection === 'positions') {
    page = (
      <PositionsPage
        positions={dashboard.positions}
        sessionUser={dashboard.sessionUser}
        actionBlockedReason={dashboard.paperActionBlockedReason}
        pausedCategories={dashboard.pausedCategories}
        onClosePosition={dashboard.closePosition}
        onResizePosition={dashboard.resizePosition}
        onMarkReview={dashboard.markPositionReview}
        onPauseCategory={dashboard.pauseCategory}
        onAddNote={dashboard.addPositionNote}
      />
    )
  }

  if (activeSection === 'paper') {
    page = (
      <PaperTradingPage
        summary={dashboard.paperSummary}
        opportunities={dashboard.paperOpportunities}
        positions={dashboard.positions}
        actionBlockedReason={dashboard.liveActionBlockedReason}
        onPromoteOpportunity={dashboard.promotePaperOpportunity}
      />
    )
  }

  if (activeSection === 'operations') {
    page = (
      <OperationsPage
        services={dashboard.services}
        logs={dashboard.logs}
        alerts={dashboard.alerts}
        killSwitchEnabled={dashboard.killSwitchEnabled}
        pausedCategories={dashboard.pausedCategories}
        lastRefreshAt={dashboard.lastRefreshAt}
        pendingKillSwitchAction={dashboard.pendingKillSwitchAction}
        onToggleKillSwitch={
          dashboard.pendingKillSwitchAction ? dashboard.executeToggleKillSwitch : dashboard.confirmToggleKillSwitch
        }
        onCancelToggle={dashboard.cancelToggleKillSwitch}
      />
    )
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <p className="brand__eyebrow">PolyClaw</p>
          <h1>Trading Desk</h1>
          <p className="muted">
            Desktop-first internal dashboard for live monitoring, paper validation, and human trade approvals.
          </p>
        </div>

        <nav className="nav-stack" aria-label="Primary">
          {navItems.map((item) => {
            const badge =
              item.id === 'opportunities'
                ? opportunityCount
                : item.id === 'positions'
                  ? positionCount
                  : item.id === 'paper'
                    ? paperCount
                    : undefined

            return (
              <button
                key={item.id}
                className={`nav-button ${activeSection === item.id ? 'is-active' : ''}`}
                type="button"
                onClick={() => setActiveSection(item.id)}
              >
                <span>{item.label}</span>
                {badge !== undefined ? <span className="nav-button__badge">{badge}</span> : null}
              </button>
            )
          })}
        </nav>

        <div className="sidebar__footer">
          <div className="sidebar__status">
            <StatusPill tone="info">Live Polymarket feed</StatusPill>
            <StatusPill tone={paperExecutionHealthy ? 'positive' : 'critical'}>
              {paperExecutionHealthy ? 'Paper execution clear' : 'Paper execution blocked'}
            </StatusPill>
          </div>
          <p className="muted">Refresh cadence: 8-12 seconds by data type</p>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div>
            <div className="topbar__status">
              <StatusPill tone="neutral">Named user auth</StatusPill>
              <StatusPill tone={dashboard.killSwitchEnabled ? 'critical' : 'positive'}>
                {dashboard.killSwitchEnabled ? 'Kill switch enabled' : 'Kill switch idle'}
              </StatusPill>
              <StatusPill tone={dashboard.liveExecutionAvailable ? 'positive' : 'warning'}>
                {dashboard.liveExecutionAvailable ? 'Live execution wired' : 'Live execution disabled'}
              </StatusPill>
              <StatusPill tone="info">Last refresh {formatRelativeTime(dashboard.lastRefreshAt)}</StatusPill>
            </div>
            <p className="muted">
              Logged in as {dashboard.sessionUser.name} · {dashboard.sessionUser.role}
            </p>
          </div>

          <div className="topbar__actions">
            <div className="user-chip">
              <strong>{dashboard.sessionUser.name}</strong>
              <span>{dashboard.sessionUser.email}</span>
            </div>
            <button className="button button--ghost" type="button" onClick={dashboard.signOut}>
              Sign out
            </button>
          </div>
        </header>

        {dashboard.paperActionBlockedReason ? (
          <div className="global-banner">
            <StatusPill tone="critical">Safety lock</StatusPill>
            <p>{dashboard.paperActionBlockedReason}</p>
          </div>
        ) : null}

        <main className="workspace__content">{page}</main>
      </div>
    </div>
  )
}

export default App
