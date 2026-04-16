// HW7 — Experiment results page showing the 3 experiments.
import { getDemoVersion } from '../lib/demoMode'
import { getDemoExperiments, getDemoBacktestQueue, getDemoRiskGateLog } from '../lib/demoData'

export function ExperimentsPage() {
  const version = getDemoVersion()
  const experiments = getDemoExperiments()
  const queue = getDemoBacktestQueue()
  const riskLog = getDemoRiskGateLog()

  if (version !== 'hw7' && version !== 'hw8') {
    return (
      <div className="experiments-page">
        <h1>Experiments</h1>
        <p className="muted">Experiment results are available in HW7 and HW8 demo modes.</p>
      </div>
    )
  }

  return (
    <div className="experiments-page">
      <h1>Agent Experiments</h1>
      <p className="muted">3 experiments with 6 agents testing strategy behavior, risk gates, and backtest reliability.</p>

      {experiments.map(exp => (
        <div key={exp.id} className="experiment-card">
          <h2>{exp.title}</h2>
          <p className="experiment-card__desc">{exp.description}</p>
          <div className="experiment-card__agents">{exp.agents_involved} agents involved</div>

          <h3>Findings</h3>
          <ul className="experiment-card__findings">
            {exp.findings.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>

          <h3>Key Metrics</h3>
          <div className="experiment-metrics">
            {Object.entries(exp.metrics).map(([k, v]) => (
              <div key={k} className="experiment-metric">
                <span className="experiment-metric__label">{k}</span>
                <span className="experiment-metric__value">{v}</span>
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* Risk Gate Log */}
      <div className="experiment-card">
        <h2>Risk Gate Enforcement Log</h2>
        <p className="experiment-card__desc">All 6 agents attempted 800 USDC orders. External agents (500 limit) were rejected. In-process agents (5000 limit) filled.</p>
        <table className="arena-leaderboard">
          <thead>
            <tr>
              <th>Agent</th>
              <th>Tier</th>
              <th>Order Size</th>
              <th>Limit</th>
              <th>Result</th>
              <th>Error Code</th>
              <th>HTTP</th>
            </tr>
          </thead>
          <tbody>
            {riskLog.map((r, i) => (
              <tr key={i} className={r.result === 'REJECTED' ? 'row-rejected' : ''}>
                <td>{r.agent_id}</td>
                <td><code>{r.tier}</code></td>
                <td>${r.order_size}</td>
                <td>${r.limit}</td>
                <td>
                  <span className={`status-pill ${r.result === 'REJECTED' ? 'status-pill--paused' : 'status-pill--active'}`}>
                    {r.result}
                  </span>
                </td>
                <td><code>{r.code || '-'}</code></td>
                <td>{r.http}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Backtest Queue */}
      <div className="experiment-card">
        <h2>Backtest Queue (SKIP LOCKED)</h2>
        <p className="experiment-card__desc">12 jobs submitted simultaneously from 6 agents (2 per agent). All 12 completed. 13th job rejected by quota gate (max_concurrent=2).</p>
        <div className="kpi-strip" style={{ marginBottom: '1rem' }}>
          <div className="kpi-card">
            <div className="kpi-card__label">Jobs Submitted</div>
            <div className="kpi-card__value">13</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-card__label">Completed</div>
            <div className="kpi-card__value positive">12</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-card__label">Rejected (429)</div>
            <div className="kpi-card__value negative">1</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-card__label">Avg Wait</div>
            <div className="kpi-card__value">4.2s</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-card__label">Duplicates</div>
            <div className="kpi-card__value positive">0</div>
          </div>
        </div>
        <table className="arena-leaderboard">
          <thead>
            <tr>
              <th>Job ID</th>
              <th>Agent</th>
              <th>Strategy</th>
              <th>Status</th>
              <th>Wait (s)</th>
            </tr>
          </thead>
          <tbody>
            {queue.map(q => (
              <tr key={q.id} className={q.status === 'failed' ? 'row-rejected' : ''}>
                <td><code>{q.id}</code></td>
                <td>{q.agent_id}</td>
                <td><code>{q.strategy}</code></td>
                <td>
                  {q.status === 'failed'
                    ? <span className="status-pill status-pill--paused">REJECTED (429)</span>
                    : <span className="status-pill status-pill--active">{q.status.toUpperCase()}</span>
                  }
                </td>
                <td>{q.status === 'failed' ? <code>quota.backtest_concurrent</code> : q.wait_seconds?.toFixed(1) ?? '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Key Takeaway */}
      <div className="experiment-card experiment-card--takeaway">
        <h2>Key Takeaway</h2>
        <p>
          The platform holds up under real multi-agent use. Risk limits work from both HTTP and
          in-process paths, the SKIP LOCKED queue serializes correctly, and different strategies
          produce measurably different outcomes on the composite leaderboard. The biggest surprise
          was mean reversion's near-zero signal rate on prediction markets — this informed the
          decision to add walk-forward analysis in the next phase.
        </p>
      </div>
    </div>
  )
}
