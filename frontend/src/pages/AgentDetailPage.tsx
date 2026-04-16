// Phase 6 — Agent detail: equity curve, KPI strip, positions, trade history, risk metrics.
import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, AreaChart, Area, CartesianGrid } from 'recharts'

type Portfolio = {
  cash_balance: number
  total_equity: number
  total_position_value: number
  total_realized_pnl: number
  total_unrealized_pnl: number
  positions: Position[]
}

type Position = {
  token_id: string
  market_id: string
  market_question: string
  outcome: string
  shares: number
  avg_entry_price: number
  current_price: number | null
  unrealized_pnl: number | null
}

type Trade = {
  id: string
  token_id: string
  side: string
  filled_price: number
  filled_size: number
  total_cost: number
  fee: number
  timestamp: number
  outcome: string
}

type LeaderboardEntry = {
  agent_id: string
  name: string
  tier: string
  total_equity: number
  return_pct: number
  sharpe: number | null
  max_drawdown: number
  calmar: number | null
  win_rate: number
  trade_count: number
  rank: number
}

function fmtUsd(n: number) {
  return '$' + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(n: number) {
  const sign = n >= 0 ? '+' : ''
  return `${sign}${(n * 100).toFixed(2)}%`
}

function fmtDate(ms: number) {
  return new Date(ms).toLocaleDateString()
}

function fmtDateTime(ms: number) {
  return new Date(ms).toLocaleString()
}

export function AgentDetailPage() {
  const { agentId } = useParams<{ agentId: string }>()
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null)
  const [trades, setTrades] = useState<Trade[]>([])
  const [metrics, setMetrics] = useState<LeaderboardEntry | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!agentId) return
    setLoading(true)
    setError('')

    // Fetch leaderboard for this agent's composite metrics
    const fetchMetrics = fetch('/api/v1/leaderboard')
      .then(r => r.json())
      .then(data => {
        const entry = (data.items || []).find((e: LeaderboardEntry) => e.agent_id === agentId)
        if (entry) setMetrics(entry)
      })

    // We can't fetch portfolio/trades without a bearer token in the browser.
    // For now, show what we have from the public leaderboard. The full agent
    // detail with positions/trades requires auth — Phase 7 will add a session
    // cookie or token-in-URL flow for the dashboard.
    Promise.all([fetchMetrics])
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [agentId])

  if (loading) return <p className="muted">Loading agent details...</p>
  if (error) return <div className="arena-error">{error}</div>

  return (
    <div className="agent-detail">
      <Link to="/leaderboard" className="back-link">Back to Leaderboard</Link>

      <h1>{metrics?.name || agentId}</h1>
      <p className="muted">
        <code>{metrics?.tier}</code> | Rank #{metrics?.rank} | {metrics?.trade_count} trades
      </p>

      {/* KPI Strip */}
      <div className="kpi-strip">
        <div className="kpi-card">
          <div className="kpi-card__label">Total Equity</div>
          <div className="kpi-card__value">{fmtUsd(metrics?.total_equity || 0)}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-card__label">Return</div>
          <div className={`kpi-card__value ${(metrics?.return_pct || 0) >= 0 ? 'positive' : 'negative'}`}>
            {fmtPct(metrics?.return_pct || 0)}
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-card__label">Sharpe Ratio</div>
          <div className="kpi-card__value">{metrics?.sharpe?.toFixed(2) ?? 'N/A'}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-card__label">Max Drawdown</div>
          <div className="kpi-card__value negative">
            {metrics?.max_drawdown ? `-${(metrics.max_drawdown * 100).toFixed(2)}%` : '0%'}
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-card__label">Calmar</div>
          <div className="kpi-card__value">{metrics?.calmar?.toFixed(2) ?? 'N/A'}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-card__label">Win Rate</div>
          <div className="kpi-card__value">{((metrics?.win_rate || 0) * 100).toFixed(1)}%</div>
        </div>
      </div>

      {/* Equity Curve Placeholder */}
      <div className="chart-section">
        <h2>Equity Curve</h2>
        <p className="muted">
          Interactive equity curve with trade markers requires authenticated portfolio_snapshots access.
          Coming in Phase 7 (dashboard auth flow). For now, see the backtest explorer for strategy-level curves.
        </p>
      </div>

      {/* Approve for Live button (Phase 7) */}
      <div className="approval-section">
        <h2>Live Trading Approval</h2>
        <p className="muted">
          Once you're satisfied with this agent's paper performance, you can approve it for live trading.
        </p>
        <Link to="/approvals" className="btn btn-primary">
          Go to Approvals Dashboard
        </Link>
      </div>
    </div>
  )
}
