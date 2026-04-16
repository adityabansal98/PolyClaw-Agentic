// Phase 6 polish — Agent detail with interactive equity curve from portfolio_snapshots.
import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  ReferenceLine,
} from 'recharts'

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

type EquityPoint = {
  ts_ms: number
  cash: number
  position_value: number
  total_equity: number
  realized_pnl: number
  unrealized_pnl: number
}

function fmtUsd(n: number) {
  return '$' + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(n: number) {
  return `${n >= 0 ? '+' : ''}${(n * 100).toFixed(2)}%`
}

function fmtDate(ms: number) {
  return new Date(ms).toLocaleDateString()
}

export function AgentDetailPage() {
  const { agentId } = useParams<{ agentId: string }>()
  const [metrics, setMetrics] = useState<LeaderboardEntry | null>(null)
  const [curve, setCurve] = useState<EquityPoint[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!agentId) return
    setLoading(true)

    const fetchMetrics = fetch('/api/v1/leaderboard')
      .then(r => r.json())
      .then(data => {
        const entry = (data.items || []).find((e: LeaderboardEntry) => e.agent_id === agentId)
        if (entry) setMetrics(entry)
      })

    const fetchCurve = fetch(`/api/v1/agents/${agentId}/equity-curve`)
      .then(r => r.json())
      .then(data => setCurve(data.points || []))

    Promise.all([fetchMetrics, fetchCurve])
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [agentId])

  if (loading) return <p className="muted">Loading agent details...</p>

  const startingBalance = curve.length > 0 ? curve[0].total_equity : (metrics?.total_equity || 10000)

  return (
    <div className="agent-detail">
      <Link to="/leaderboard" className="back-link">&larr; Back to Leaderboard</Link>

      <h1>{metrics?.name || agentId}</h1>
      <p className="muted">
        <code>{metrics?.tier}</code> &middot; Rank #{metrics?.rank} &middot; {metrics?.trade_count} trades
      </p>

      {/* KPI Strip */}
      <div className="kpi-strip">
        <KpiCard label="Total Equity" value={fmtUsd(metrics?.total_equity || 0)} />
        <KpiCard label="Return" value={fmtPct(metrics?.return_pct || 0)}
                 className={(metrics?.return_pct || 0) >= 0 ? 'positive' : 'negative'} />
        <KpiCard label="Sharpe Ratio" value={metrics?.sharpe?.toFixed(2) ?? 'N/A'} />
        <KpiCard label="Max Drawdown"
                 value={metrics?.max_drawdown ? `-${(metrics.max_drawdown * 100).toFixed(2)}%` : '0%'}
                 className="negative" />
        <KpiCard label="Calmar" value={metrics?.calmar?.toFixed(2) ?? 'N/A'} />
        <KpiCard label="Win Rate" value={`${((metrics?.win_rate || 0) * 100).toFixed(1)}%`} />
      </div>

      {/* Equity Curve */}
      <div className="chart-section">
        <h2>Equity Curve</h2>
        {curve.length > 1 ? (
          <ResponsiveContainer width="100%" height={350}>
            <AreaChart data={curve} margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
              <defs>
                <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#818cf8" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#818cf8" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis
                dataKey="ts_ms"
                tickFormatter={fmtDate}
                stroke="#6b7280"
                fontSize={11}
              />
              <YAxis
                tickFormatter={(v: number) => `$${(v / 1000).toFixed(1)}k`}
                stroke="#6b7280"
                fontSize={11}
              />
              <Tooltip
                formatter={(value: number) => [fmtUsd(value), 'Equity']}
                labelFormatter={(label: number) => new Date(label).toLocaleString()}
                contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
              />
              <ReferenceLine y={startingBalance} stroke="#6b7280" strokeDasharray="3 3" />
              <Area
                type="monotone"
                dataKey="total_equity"
                stroke="#818cf8"
                fill="url(#equityGrad)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <p className="muted">No portfolio snapshots yet. Trade to generate data.</p>
        )}
      </div>

      {/* Cash vs Position breakdown */}
      {curve.length > 1 && (
        <div className="chart-section">
          <h2>Cash vs Position Value</h2>
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={curve} margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="ts_ms" tickFormatter={fmtDate} stroke="#6b7280" fontSize={11} />
              <YAxis tickFormatter={(v: number) => `$${(v / 1000).toFixed(1)}k`} stroke="#6b7280" fontSize={11} />
              <Tooltip
                contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
                formatter={(value: number, name: string) => [fmtUsd(value), name]}
                labelFormatter={(label: number) => new Date(label).toLocaleString()}
              />
              <Area type="monotone" dataKey="cash" stackId="1" stroke="#10b981" fill="#10b981" fillOpacity={0.3} />
              <Area type="monotone" dataKey="position_value" stackId="1" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.3} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Actions */}
      <div className="approval-section">
        <h2>Live Trading</h2>
        <Link to="/approvals" className="btn btn-primary">Go to Approvals Dashboard</Link>
      </div>
    </div>
  )
}

function KpiCard({ label, value, className = '' }: { label: string; value: string; className?: string }) {
  return (
    <div className="kpi-card">
      <div className="kpi-card__label">{label}</div>
      <div className={`kpi-card__value ${className}`}>{value}</div>
    </div>
  )
}
