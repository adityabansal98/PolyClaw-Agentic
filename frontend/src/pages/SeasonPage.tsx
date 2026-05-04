// HW8 — Season details page with walk-forward analysis, Monte Carlo, safety breakers.
import { getDemoVersion } from '../lib/demoMode'
import {
  getDemoSeason, getDemoWalkForward, getDemoMonteCarlo,
  getDemoAgents, getDemoStats,
  getDemoOrderRejections, getDemoSafetyEvents,
} from '../lib/demoData'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  Cell, ReferenceLine, Legend,
} from 'recharts'

export function SeasonPage() {
  const version = getDemoVersion()

  if (version !== 'hw8') {
    return (
      <div className="season-page">
        <h1>Season</h1>
        <p className="muted">Season data is available in HW8 demo mode.</p>
      </div>
    )
  }

  const season = getDemoSeason()
  const walkForward = getDemoWalkForward()
  const monteCarlo = getDemoMonteCarlo()
  const agents = getDemoAgents('hw8')
  // stats used for season overview
  void getDemoStats('hw8')

  const pausedAgent = agents.find(a => a.status === 'paused')

  // Monte Carlo summary
  const mcWithinCi = monteCarlo.filter(m => m.within_ci).length
  const mcTotal = monteCarlo.length

  // Walk-forward chart data
  const wfChartData = walkForward.map(w => ({
    name: w.agent_name,
    in_sample: Math.round(w.in_sample_return * 1000) / 10,
    out_of_sample: Math.round(w.out_of_sample_return * 1000) / 10,
    overfit: Math.round(w.overfit_score * 100),
    flagged: w.flagged,
  }))

  // Tier breakdown
  const tiers = {
    hosted_inprocess: agents.filter(a => a.tier === 'hosted_inprocess'),
    external_http: agents.filter(a => a.tier === 'external_http'),
    external_mcp: agents.filter(a => a.tier === 'external_mcp'),
  }

  return (
    <div className="season-page">
      <h1>{season.name}</h1>

      {/* Season Info */}
      <div className="season-info">
        <div className="kpi-strip">
          <div className="kpi-card">
            <div className="kpi-card__label">Status</div>
            <div className="kpi-card__value">
              <span className={`status-pill status-pill--${season.status}`}>{season.status.toUpperCase()}</span>
            </div>
          </div>
          <div className="kpi-card">
            <div className="kpi-card__label">Agents</div>
            <div className="kpi-card__value">{season.agent_count}</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-card__label">Starting Balance</div>
            <div className="kpi-card__value">${season.starting_balance.toLocaleString()}</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-card__label">Universe</div>
            <div className="kpi-card__value">{season.market_universe_filter}</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-card__label">Duration</div>
            <div className="kpi-card__value">2 weeks</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-card__label">Mode</div>
            <div className="kpi-card__value">{season.mode}</div>
          </div>
        </div>
      </div>

      {/* Tier Breakdown */}
      <div className="experiment-card">
        <h2>Agent Tier Breakdown</h2>
        <div className="tier-breakdown">
          <div className="tier-box">
            <div className="tier-box__count">{tiers.hosted_inprocess.length}</div>
            <div className="tier-box__label">House Agents</div>
            <div className="tier-box__detail">hosted_inprocess</div>
            <div className="tier-box__desc">5 momentum variants, 3 Kelly variants, 2 fade-longshot. Running in-process on Railway worker.</div>
          </div>
          <div className="tier-box">
            <div className="tier-box__count">{tiers.external_http.length}</div>
            <div className="tier-box__label">External HTTP</div>
            <div className="tier-box__detail">external_http</div>
            <div className="tier-box__desc">Running on separate cloud instances, calling /api/v1/orders with bearer tokens. Mix of custom strategies.</div>
          </div>
          <div className="tier-box">
            <div className="tier-box__count">{tiers.external_mcp.length}</div>
            <div className="tier-box__label">MCP Agents</div>
            <div className="tier-box__detail">external_mcp</div>
            <div className="tier-box__desc">Connected via Claude Desktop using the MCP server tool chain.</div>
          </div>
        </div>
      </div>

      {/* Walk-Forward Analysis */}
      <div className="experiment-card">
        <h2>Walk-Forward Analysis</h2>
        <p className="experiment-card__desc">
          Splits data into train/test windows. Agents with overfit score &gt; 0.7 are flagged.
          <strong> {walkForward.filter(w => w.flagged).length} agents flagged</strong> for overfitting.
        </p>

        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={wfChartData} margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="name" stroke="#6b7280" fontSize={11} />
            <YAxis stroke="#6b7280" fontSize={11} tickFormatter={(v: number) => `${v}%`} />
            <Tooltip
              contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
              formatter={(value: any) => [`${value}%`]}
            />
            <Legend />
            <ReferenceLine y={0} stroke="#6b7280" />
            <Bar dataKey="in_sample" name="In-Sample Return" fill="#818cf8" />
            <Bar dataKey="out_of_sample" name="Out-of-Sample Return">
              {wfChartData.map((entry, i) => (
                <Cell key={i} fill={entry.flagged ? '#ef4444' : '#10b981'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>

        <table className="arena-leaderboard" style={{ marginTop: '1rem' }}>
          <thead>
            <tr>
              <th>Agent</th>
              <th>In-Sample</th>
              <th>Out-of-Sample</th>
              <th>Overfit Score</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {walkForward.map(w => (
              <tr key={w.agent_id} className={w.flagged ? 'row-rejected' : ''}>
                <td>{w.agent_name}</td>
                <td className="arena-pnl-positive">+{(w.in_sample_return * 100).toFixed(1)}%</td>
                <td className={w.out_of_sample_return >= 0 ? 'arena-pnl-positive' : 'arena-pnl-negative'}>
                  {(w.out_of_sample_return * 100).toFixed(1)}%
                </td>
                <td>{w.overfit_score.toFixed(2)}</td>
                <td>
                  {w.flagged
                    ? <span className="status-pill status-pill--paused">OVERFITTING</span>
                    : <span className="status-pill status-pill--active">HEALTHY</span>
                  }
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Monte Carlo */}
      <div className="experiment-card">
        <h2>Monte Carlo Simulation</h2>
        <p className="experiment-card__desc">
          1000x bootstrap resampling of trades to produce 90% confidence intervals.
          <strong> {mcWithinCi}/{mcTotal} agents</strong> had actual returns within the CI.
        </p>

        <div className="kpi-strip" style={{ marginBottom: '1rem' }}>
          <div className="kpi-card">
            <div className="kpi-card__label">Simulations</div>
            <div className="kpi-card__value">1,000x</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-card__label">Within 90% CI</div>
            <div className="kpi-card__value positive">{mcWithinCi}/{mcTotal}</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-card__label">Accuracy</div>
            <div className="kpi-card__value">{((mcWithinCi / mcTotal) * 100).toFixed(0)}%</div>
          </div>
        </div>

        <div className="mc-table-scroll">
          <table className="arena-leaderboard">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Actual Return</th>
                <th>90% CI Low</th>
                <th>90% CI High</th>
                <th>Within CI</th>
                <th>P(Ruin)</th>
              </tr>
            </thead>
            <tbody>
              {monteCarlo.slice(0, 15).map(m => (
                <tr key={m.agent_id}>
                  <td>{m.agent_name}</td>
                  <td className={m.actual_return >= 0 ? 'arena-pnl-positive' : 'arena-pnl-negative'}>
                    {(m.actual_return * 100).toFixed(2)}%
                  </td>
                  <td>{(m.ci_low * 100).toFixed(2)}%</td>
                  <td>{(m.ci_high * 100).toFixed(2)}%</td>
                  <td>{m.within_ci ? 'Yes' : <span className="arena-pnl-negative">No</span>}</td>
                  <td className={m.prob_of_ruin > 0.1 ? 'arena-pnl-negative' : ''}>{(m.prob_of_ruin * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {monteCarlo.length > 15 && (
          <p className="muted" style={{ marginTop: '0.5rem' }}>Showing top 15 of {monteCarlo.length} agents.</p>
        )}
      </div>

      {/* Safety Breaker */}
      {pausedAgent && (() => {
        const safetyEvents = getDemoSafetyEvents()
        const orderRejections = getDemoOrderRejections()
        return (
        <div className="experiment-card experiment-card--danger">
          <h2>Safety Circuit Breaker Triggered</h2>
          <p className="experiment-card__desc">
            Agent <strong>{pausedAgent.name}</strong> (aggressive momentum variant with 3x Kelly sizing)
            tripped the drawdown breaker.
          </p>
          <div className="kpi-strip" style={{ marginBottom: '1rem' }}>
            <div className="kpi-card">
              <div className="kpi-card__label">Agent</div>
              <div className="kpi-card__value">{pausedAgent.name}</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-card__label">Max Drawdown</div>
              <div className="kpi-card__value negative">-{(pausedAgent.max_drawdown * 100).toFixed(1)}%</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-card__label">Final Equity</div>
              <div className="kpi-card__value negative">${pausedAgent.total_equity.toLocaleString()}</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-card__label">Kill Switch</div>
              <div className="kpi-card__value">4.8s</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-card__label">Status</div>
              <div className="kpi-card__value"><span className="status-pill status-pill--paused">PAUSED</span></div>
            </div>
          </div>

          {/* Safety event timeline */}
          <h3>Event Timeline</h3>
          <div className="safety-timeline">
            {safetyEvents.map((e, i) => (
              <div key={i} className="safety-event">
                <div className="safety-event__marker" />
                <div className="safety-event__content">
                  <div className="safety-event__title">{e.event}</div>
                  <div className="safety-event__detail">{e.details}</div>
                  <div className="safety-event__time">{new Date(e.ts_ms).toLocaleString()}</div>
                </div>
              </div>
            ))}
          </div>

          {/* Order rejections after pause */}
          <h3>Subsequent Order Rejections</h3>
          <table className="arena-leaderboard">
            <thead>
              <tr>
                <th>Time</th>
                <th>Agent</th>
                <th>Order Size</th>
                <th>Error Code</th>
                <th>HTTP</th>
              </tr>
            </thead>
            <tbody>
              {orderRejections.map((r, i) => (
                <tr key={i} className="row-rejected">
                  <td className="muted">{new Date(r.ts_ms).toLocaleString()}</td>
                  <td>{r.agent_name}</td>
                  <td>${r.order_size}</td>
                  <td><code>{r.error_code}</code></td>
                  <td><span className="status-pill status-pill--paused">{r.http_status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        )
      })()}

      {/* Bottlenecks */}
      <div className="experiment-card">
        <h2>Bottlenecks & Performance</h2>
        <div className="bottleneck-grid">
          <div className="bottleneck-item">
            <h3>Database under load</h3>
            <p>Platform slowed down when 30 agents traded at once — had to switch databases mid-project. SQLite was 4.2s per portfolio sampler tick (file lock serialized all 30 snapshot writes); Postgres dropped that to 0.8s.</p>
            <div className="bottleneck-item__fix">Fix: dropped SQLite from the worker hot path. Postgres-only for production. SQLite still works for dev.</div>
          </div>
          <div className="bottleneck-item">
            <h3>Backtest queue throughput</h3>
            <p>Designed for single-threaded backtesting — didn't plan for 30 agents queuing at once. With one worker, 30 × walk-forward + Monte Carlo jobs backed up to ~22 minutes queue depth.</p>
            <div className="bottleneck-item__fix">Fix needed: horizontal workers (multiple Railway instances claiming from the same SKIP LOCKED queue). Architecture supports it; just needs to be turned on.</div>
          </div>
          <div className="bottleneck-item">
            <h3>Strategy quality monitoring</h3>
            <p>Some agents ran bad strategies and the platform had no way to flag it early. Composite leaderboard surfaces it after the fact, but there's no mid-season "this agent looks suspect" alert.</p>
            <div className="bottleneck-item__fix">Fix needed: real-time strategy degradation detection (rolling Sharpe drop, drawdown velocity, signal entropy collapse).</div>
          </div>
          <div className="bottleneck-item">
            <h3>Resource usage</h3>
            <p>~6,000 paper trades + ~60 backtest runs. Postgres storage: ~2MB. Worker CPU: under 20% on Railway $5/mo.</p>
            <div className="bottleneck-item__fix">Main cost driver: CLOB API calls for orderbook fetches (~4,000/day at 60s cadence).</div>
          </div>
        </div>
      </div>

      {/* Grid Search Results */}
      <div className="experiment-card">
        <h2>Parameter Optimization (Grid Search)</h2>
        <p className="experiment-card__desc">
          Agents search strategy parameter space before committing. Best result: momentum with 7-tick
          short window outperformed default 10-tick by 2.3% on NBA markets.
        </p>
        <table className="arena-leaderboard">
          <thead>
            <tr>
              <th>Strategy</th>
              <th>Parameter</th>
              <th>Default</th>
              <th>Best Found</th>
              <th>Improvement</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><code>momentum</code></td>
              <td>short_window</td>
              <td>10 ticks</td>
              <td className="arena-pnl-positive">7 ticks</td>
              <td className="arena-pnl-positive">+2.3%</td>
            </tr>
            <tr>
              <td><code>kelly_sized</code></td>
              <td>kelly_fraction</td>
              <td>0.25 (quarter)</td>
              <td className="arena-pnl-positive">0.35</td>
              <td className="arena-pnl-positive">+1.1%</td>
            </tr>
            <tr>
              <td><code>fade_longshot</code></td>
              <td>threshold</td>
              <td>0.08</td>
              <td>0.06</td>
              <td className="arena-pnl-positive">+0.8%</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Key Takeaway */}
      <div className="experiment-card experiment-card--takeaway">
        <h2>Key Takeaway</h2>
        <p>
          The platform handles 30 concurrent agents without data corruption or lost trades.
          Multi-tenant isolation (agent_id scoping + SELECT FOR UPDATE cash debits) held up.
          The bottleneck is compute, not correctness: the single-threaded backtest worker can't
          keep up with 30 agents submitting walk-forward + Monte Carlo jobs simultaneously.
          The fix is worker parallelism — the architecture already supports it.
        </p>
      </div>
    </div>
  )
}
