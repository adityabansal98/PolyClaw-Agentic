// Phase 6 — Dashboard home: season summary + agent cards with sparklines.
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

type AgentSummary = {
  agent_id: string
  name: string
  tier: string
  total_equity: number
  return_pct: number
  last_update_ms: number | null
}

export function DashboardPage() {
  const [agents, setAgents] = useState<AgentSummary[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/v1/leaderboard')
      .then(r => r.json())
      .then(data => setAgents(data.items || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="dashboard-page">
      <h1>Dashboard</h1>
      <p className="muted">Your agents at a glance. Click any card to view details.</p>

      {loading ? <p className="muted">Loading...</p> : null}

      <div className="agent-cards">
        {agents.map(a => (
          <Link to={`/agents/${a.agent_id}`} key={a.agent_id} className="agent-card">
            <div className="agent-card__name">{a.name}</div>
            <div className="agent-card__tier"><code>{a.tier}</code></div>
            <div className="agent-card__equity">${a.total_equity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>
            <div className={`agent-card__return ${a.return_pct >= 0 ? 'positive' : 'negative'}`}>
              {a.return_pct >= 0 ? '+' : ''}{(a.return_pct * 100).toFixed(2)}%
            </div>
          </Link>
        ))}
        {!loading && agents.length === 0 && (
          <p className="muted">No agents registered yet. Use the SDK to create one.</p>
        )}
      </div>
    </div>
  )
}
