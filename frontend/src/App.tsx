// Phase 6 rewrite — React Router + sidebar navigation.
// Demo mode: ?demo=hw6|hw7|hw8 shows version-appropriate nav items.
import './App.css'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { DashboardPage } from './pages/DashboardPage'
import { AgentDetailPage } from './pages/AgentDetailPage'
import { LeaderboardPage } from './pages/LeaderboardPage'
import { BacktestPage } from './pages/BacktestPage'
import { ApprovalsPage } from './pages/ApprovalsPage'
import { ExperimentsPage } from './pages/ExperimentsPage'
import { SeasonPage } from './pages/SeasonPage'
import { getDemoVersion } from './lib/demoMode'

function DemoNav() {
  const version = getDemoVersion()
  const q = version ? `?demo=${version}` : ''

  return (
    <nav className="sidebar">
      <div className="sidebar__logo">PolyClaw</div>
      <NavLink to={`/${q}`} className="sidebar__link" end>Dashboard</NavLink>
      <NavLink to={`/leaderboard${q}`} className="sidebar__link">Leaderboard</NavLink>
      <NavLink to={`/backtest${q}`} className="sidebar__link">Backtest</NavLink>
      {(version === 'hw7' || version === 'hw8') && (
        <NavLink to={`/experiments${q}`} className="sidebar__link">Experiments</NavLink>
      )}
      {version === 'hw8' && (
        <NavLink to={`/season${q}`} className="sidebar__link">Season</NavLink>
      )}
      <NavLink to={`/approvals${q}`} className="sidebar__link">Approvals</NavLink>

      {/* View switcher — always visible. The 30-agent stress test is the default. */}
      <div className="sidebar__switcher">
        <div className="sidebar__switcher-label">View</div>
        <a href="/?demo=hw6" className={`sidebar__switch-btn ${version === 'hw6' ? 'active' : ''}`}>Platform Tour</a>
        <a href="/?demo=hw7" className={`sidebar__switch-btn ${version === 'hw7' ? 'active' : ''}`}>Strategy Lab</a>
        <a href="/?demo=hw8" className={`sidebar__switch-btn ${version === 'hw8' ? 'active' : ''}`}>Stress Test Season</a>
        <a href="/?demo=none" className={`sidebar__switch-btn ${version === null ? 'active' : ''}`}>Live API</a>
      </div>
    </nav>
  )
}

function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <DemoNav />
        <div className="workspace">
          <main className="workspace__content">
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/leaderboard" element={<LeaderboardPage />} />
              <Route path="/agents/:agentId" element={<AgentDetailPage />} />
              <Route path="/backtest" element={<BacktestPage />} />
              <Route path="/approvals" element={<ApprovalsPage />} />
              <Route path="/experiments" element={<ExperimentsPage />} />
              <Route path="/season" element={<SeasonPage />} />
            </Routes>
          </main>
        </div>
      </div>
    </BrowserRouter>
  )
}

export default App
