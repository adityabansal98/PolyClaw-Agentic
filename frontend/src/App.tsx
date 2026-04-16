// Phase 6 rewrite — React Router + sidebar navigation.
import './App.css'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { DashboardPage } from './pages/DashboardPage'
import { AgentDetailPage } from './pages/AgentDetailPage'
import { LeaderboardPage } from './pages/LeaderboardPage'
import { BacktestPage } from './pages/BacktestPage'
import { ApprovalsPage } from './pages/ApprovalsPage'

function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <nav className="sidebar">
          <div className="sidebar__logo">PolyClaw</div>
          <NavLink to="/" className="sidebar__link" end>Dashboard</NavLink>
          <NavLink to="/leaderboard" className="sidebar__link">Leaderboard</NavLink>
          <NavLink to="/backtest" className="sidebar__link">Backtest</NavLink>
          <NavLink to="/approvals" className="sidebar__link">Approvals</NavLink>
        </nav>
        <div className="workspace">
          <main className="workspace__content">
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/leaderboard" element={<LeaderboardPage />} />
              <Route path="/agents/:agentId" element={<AgentDetailPage />} />
              <Route path="/backtest" element={<BacktestPage />} />
              <Route path="/approvals" element={<ApprovalsPage />} />
            </Routes>
          </main>
        </div>
      </div>
    </BrowserRouter>
  )
}

export default App
