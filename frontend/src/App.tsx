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
import { DocsPage } from './pages/DocsPage'
import { getDemoVersion } from './lib/demoMode'

function DemoNav() {
  const version = getDemoVersion()
  const q = version ? `?demo=${version}` : ''

  return (
    <nav className="sidebar">
      <div className="sidebar__logo">PolyClaw</div>
      <NavLink to={`/${q}`} className="sidebar__link" end>Dashboard</NavLink>
      <NavLink to="/docs" className="sidebar__link sidebar__link--accent">Get Started</NavLink>
      <NavLink to={`/leaderboard${q}`} className="sidebar__link">Leaderboard</NavLink>
      <NavLink to={`/backtest${q}`} className="sidebar__link">Backtest</NavLink>
      {(version === 'hw7' || version === 'hw8') && (
        <NavLink to={`/experiments${q}`} className="sidebar__link">Experiments</NavLink>
      )}
      {version === 'hw8' && (
        <NavLink to={`/season${q}`} className="sidebar__link">Season</NavLink>
      )}
      <NavLink to={`/approvals${q}`} className="sidebar__link">Approvals</NavLink>
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
              <Route path="/docs" element={<DocsPage />} />
            </Routes>
          </main>
        </div>
      </div>
    </BrowserRouter>
  )
}

export default App
