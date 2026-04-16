// Phase 6 — Dashboard home: season summary + agent cards with sparklines.
// Demo mode: renders mock data when ?demo=hw6|hw7|hw8 is in URL.
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getDemoVersion, type DemoVersion } from '../lib/demoMode'
import { getDemoAgents, getDemoStats, getDemoSeason, HW6_SYSTEM_INFO } from '../lib/demoData'

type AgentSummary = {
  agent_id: string
  name: string
  tier: string
  total_equity: number
  return_pct: number
  last_update_ms: number | null
  status?: string
  strategy?: string
  pause_reason?: string
}

function VersionBadge({ version }: { version: DemoVersion }) {
  if (!version) return null
  const labels: Record<string, string> = {
    hw6: 'HW6: MVP Demo',
    hw7: 'HW7: 6-Agent Experiments',
    hw8: 'HW8: 30-Agent Scaled Test',
  }
  return (
    <div className="demo-badge">
      {labels[version]}
    </div>
  )
}

export function DashboardPage() {
  const [agents, setAgents] = useState<AgentSummary[]>([])
  const [loading, setLoading] = useState(true)
  const version = getDemoVersion()

  useEffect(() => {
    if (version) {
      const demoAgents = getDemoAgents(version)
      setAgents(demoAgents.map(a => ({
        ...a,
        last_update_ms: Date.now() - Math.random() * 3600000,
      })))
      setLoading(false)
      return
    }
    fetch('/api/v1/leaderboard')
      .then(r => r.json())
      .then(data => setAgents(data.items || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [version])

  const stats = version ? getDemoStats(version) : null
  const season = version === 'hw8' ? getDemoSeason() : null

  return (
    <div className="dashboard-page">
      <VersionBadge version={version} />
      <h1>Dashboard</h1>

      {/* HW8: Season banner */}
      {season && (
        <div className="season-banner">
          <div className="season-banner__title">{season.name}</div>
          <div className="season-banner__meta">
            <span className={`status-pill status-pill--${season.status}`}>{season.status.toUpperCase()}</span>
            <span>{season.agent_count} agents</span>
            <span>${season.starting_balance.toLocaleString()} starting balance</span>
            <span>{season.market_universe_filter}</span>
            <span>{season.mode} mode</span>
          </div>
        </div>
      )}

      {/* Stats strip */}
      {stats && (
        <div className="kpi-strip">
          <div className="kpi-card">
            <div className="kpi-card__label">Agents</div>
            <div className="kpi-card__value">{stats.agentCount}</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-card__label">Total Equity</div>
            <div className="kpi-card__value">${stats.totalEquity.toLocaleString(undefined, {maximumFractionDigits: 0})}</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-card__label">Total Trades</div>
            <div className="kpi-card__value">{stats.totalTrades.toLocaleString()}</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-card__label">Avg Return</div>
            <div className={`kpi-card__value ${stats.avgReturn >= 0 ? 'positive' : 'negative'}`}>
              {stats.avgReturn >= 0 ? '+' : ''}{(stats.avgReturn * 100).toFixed(2)}%
            </div>
          </div>
          {version === 'hw8' && (
            <>
              <div className="kpi-card">
                <div className="kpi-card__label">Active</div>
                <div className="kpi-card__value positive">{stats.activeCount}</div>
              </div>
              <div className="kpi-card">
                <div className="kpi-card__label">Paused</div>
                <div className="kpi-card__value negative">{stats.pausedCount}</div>
              </div>
            </>
          )}
        </div>
      )}

      <p className="muted">
        {version === 'hw6' && 'Your agents at a glance. Click any card to view details.'}
        {version === 'hw7' && '6 agents running 3 strategies (Momentum, Mean Reversion, Kelly). Click any card for details.'}
        {version === 'hw8' && '30 agents competing in Stress Test Season. 10 house, 12 external HTTP, 8 MCP agents.'}
        {!version && 'Your agents at a glance. Click any card to view details.'}
      </p>

      {loading ? <p className="muted">Loading...</p> : null}

      <div className="agent-cards">
        {agents.map(a => (
          <Link to={`/agents/${a.agent_id}${version ? `?demo=${version}` : ''}`} key={a.agent_id} className={`agent-card ${a.status === 'paused' ? 'agent-card--paused' : ''}`}>
            <div className="agent-card__header">
              <div className="agent-card__name">{a.name}</div>
              {a.status === 'paused' && <span className="status-pill status-pill--paused">PAUSED</span>}
            </div>
            <div className="agent-card__tier"><code>{a.tier}</code></div>
            {a.strategy && <div className="agent-card__strategy">{a.strategy}</div>}
            <div className="agent-card__equity">${a.total_equity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>
            <div className={`agent-card__return ${a.return_pct >= 0 ? 'positive' : 'negative'}`}>
              {a.return_pct >= 0 ? '+' : ''}{(a.return_pct * 100).toFixed(2)}%
            </div>
            {a.pause_reason && <div className="agent-card__pause-reason">{a.pause_reason}</div>}
          </Link>
        ))}
        {!loading && agents.length === 0 && (
          <p className="muted">No agents registered yet. Use the SDK to create one.</p>
        )}
      </div>

      {/* HW6: System Info — API, Auth, Tests, Audit, Deployment */}
      {version === 'hw6' && (
        <div className="system-info">
          <div className="experiment-card">
            <h2>API Endpoints ({HW6_SYSTEM_INFO.endpoints.length} authenticated under /api/v1/)</h2>
            <table className="arena-leaderboard">
              <thead>
                <tr><th>Method</th><th>Path</th><th>Description</th></tr>
              </thead>
              <tbody>
                {HW6_SYSTEM_INFO.endpoints.map((e, i) => (
                  <tr key={i}>
                    <td><code>{e.method}</code></td>
                    <td><code>{e.path}</code></td>
                    <td>{e.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="experiment-card">
            <h2>Authentication</h2>
            <div className="kpi-strip">
              <div className="kpi-card"><div className="kpi-card__label">Type</div><div className="kpi-card__value">{HW6_SYSTEM_INFO.auth.type}</div></div>
              <div className="kpi-card"><div className="kpi-card__label">Header</div><div className="kpi-card__value" style={{fontSize:'0.7rem'}}>{HW6_SYSTEM_INFO.auth.header}</div></div>
            </div>
            <p className="muted" style={{marginTop:'0.5rem'}}>{HW6_SYSTEM_INFO.auth.flow}</p>
          </div>

          <div className="experiment-card">
            <h2>Audit Trail</h2>
            <p className="experiment-card__desc">Every trade is recorded with a full audit trail enabling byte-identical replay.</p>
            <div className="experiment-metrics">
              {HW6_SYSTEM_INFO.audit.fields.map(f => (
                <div key={f} className="experiment-metric">
                  <span className="experiment-metric__value"><code>{f}</code></span>
                </div>
              ))}
            </div>
            <p className="muted" style={{marginTop:'0.5rem'}}>{HW6_SYSTEM_INFO.audit.replay}</p>
          </div>

          <div className="experiment-card">
            <h2>Testing</h2>
            <div className="kpi-strip">
              <div className="kpi-card"><div className="kpi-card__label">Tests</div><div className="kpi-card__value positive">{HW6_SYSTEM_INFO.tests.total} passing</div></div>
              <div className="kpi-card"><div className="kpi-card__label">Framework</div><div className="kpi-card__value">{HW6_SYSTEM_INFO.tests.framework}</div></div>
              <div className="kpi-card"><div className="kpi-card__label">Databases</div><div className="kpi-card__value">{HW6_SYSTEM_INFO.tests.databases.join(' + ')}</div></div>
            </div>
            <p className="muted" style={{marginTop:'0.5rem'}}>{HW6_SYSTEM_INFO.tests.key_test}</p>
          </div>

          <div className="experiment-card">
            <h2>Deployment</h2>
            <div className="tier-breakdown">
              {Object.entries(HW6_SYSTEM_INFO.deployment).map(([k, v]) => (
                <div key={k} className="tier-box">
                  <div className="tier-box__label">{k.charAt(0).toUpperCase() + k.slice(1)}</div>
                  <div className="tier-box__detail">{v}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
