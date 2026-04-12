import { formatCompactCurrency, formatCurrency, formatPercent, formatRelativeTime, formatSignedCurrency } from '../lib/format'
import type { AlertItem, Opportunity, PortfolioSummary, Position, ServiceHealth } from '../lib/types'
import { KpiCard } from '../components/KpiCard'
import { Panel } from '../components/Panel'
import { StatusPill } from '../components/StatusPill'

interface OverviewPageProps {
  liveSummary: PortfolioSummary
  paperSummary: PortfolioSummary
  opportunities: Opportunity[]
  positions: Position[]
  alerts: AlertItem[]
  services: ServiceHealth[]
  lastRefreshAt: string
  onNavigate: (target: 'opportunities' | 'positions' | 'paper' | 'operations') => void
}

export function OverviewPage({
  liveSummary,
  paperSummary,
  opportunities,
  positions,
  alerts,
  services,
  lastRefreshAt,
  onNavigate,
}: OverviewPageProps) {
  const topOpportunities = opportunities
    .filter((opportunity) => opportunity.currentStage !== 'rejected')
    .slice(0, 5)

  const criticalServices = services.filter((service) => service.critical)
  const exposureByCategory = positions.reduce<Record<string, number>>((acc, position) => {
    acc[position.category] = (acc[position.category] ?? 0) + position.stake
    return acc
  }, {})

  const exposureRows = Object.entries(exposureByCategory).sort((a, b) => b[1] - a[1])
  const maxExposure = exposureRows[0]?.[1] ?? 1

  return (
    <div className="page-stack">
      <div className="hero-strip">
        <div>
          <p className="eyebrow">Overview</p>
          <h1>Portfolio control and pre-trade decision flow</h1>
          <p className="muted">
            Auto-refresh is on. Last full refresh {formatRelativeTime(lastRefreshAt)} with separate live and paper
            views.
          </p>
        </div>
        <div className="hero-strip__actions">
          <button className="button button--ghost" type="button" onClick={() => onNavigate('opportunities')}>
            Review opportunities
          </button>
          <button className="button button--primary" type="button" onClick={() => onNavigate('positions')}>
            Inspect live positions
          </button>
        </div>
      </div>

      <section className="kpi-grid">
        <KpiCard
          label="Total return if liquidated now"
          value={formatCurrency(liveSummary.totalReturnImmediate)}
          delta={formatSignedCurrency(liveSummary.dailyPnl)}
          helper="Live book mark-to-market"
          trend={positions.slice(0, 3).flatMap((position) => position.priceHistory.slice(-2))}
          tone="amber"
          emphasis
        />
        <KpiCard
          label="Open exposure"
          value={formatCurrency(liveSummary.openExposure)}
          delta={`${liveSummary.activePositions} live positions`}
          helper="Committed live notional"
          trend={positions.map((position) => position.stake / 10000)}
          tone="blue"
        />
        <KpiCard
          label="Available capital"
          value={formatCurrency(liveSummary.availableCapital)}
          delta={`${liveSummary.pendingApprovals} awaiting review`}
          helper="Cash available for new live approvals"
          trend={[
            liveSummary.availableCapital / 100000,
            (liveSummary.availableCapital - 1800) / 100000,
            liveSummary.availableCapital / 100000,
          ]}
          tone="teal"
        />
        <KpiCard
          label="Paper PnL"
          value={formatCurrency(paperSummary.totalReturnImmediate)}
          delta={formatSignedCurrency(paperSummary.dailyPnl)}
          helper="Validation before live promotion"
          trend={positions.slice(0, 2).flatMap((position) => position.priceHistory.slice(-2))}
          tone="blue"
        />
      </section>

      <section className="overview-grid">
        <Panel
          title="Action board"
          subtitle="What needs human attention right now"
          action={
            <button className="button button--ghost" type="button" onClick={() => onNavigate('operations')}>
              Open operations
            </button>
          }
        >
          <div className="alert-stack">
            {alerts.map((alert) => (
              <article key={alert.id} className={`alert-card alert-card--${alert.tone}`}>
                <div>
                  <p className="alert-card__title">{alert.title}</p>
                  <p className="muted">{alert.description}</p>
                </div>
              </article>
            ))}
          </div>
        </Panel>

        <Panel
          title="Top opportunities"
          subtitle="Highest-signal candidate bets requiring review"
          action={
            <button className="button button--primary" type="button" onClick={() => onNavigate('opportunities')}>
              Open queue
            </button>
          }
        >
          <div className="list-stack">
            {topOpportunities.map((opportunity) => (
              <article key={opportunity.id} className="list-row">
                <div className="list-row__main">
                  <p className="list-row__title">{opportunity.question}</p>
                  <p className="muted">
                    {opportunity.category} · {opportunity.marketType}
                  </p>
                </div>
                <div className="list-row__meta">
                  <StatusPill tone="info">{opportunity.statusLabel}</StatusPill>
                  <span>{formatPercent(opportunity.expectedReturn)}</span>
                </div>
              </article>
            ))}
          </div>
        </Panel>
      </section>

      <section className="overview-grid overview-grid--dense">
        <Panel
          title="Live positions"
          subtitle="Existing book with current mark-to-market"
          action={
            <button className="button button--ghost" type="button" onClick={() => onNavigate('positions')}>
              View all
            </button>
          }
        >
          <div className="table-shell">
            <table>
              <thead>
                <tr>
                  <th>Market</th>
                  <th>Category</th>
                  <th>Exposure</th>
                  <th>Liquidation</th>
                  <th>Unrealized</th>
                </tr>
              </thead>
              <tbody>
                {positions.slice(0, 4).map((position) => (
                  <tr key={position.id}>
                    <td>{position.question}</td>
                    <td>{position.category}</td>
                    <td>{formatCurrency(position.stake)}</td>
                    <td>{formatCurrency(position.liquidationValue)}</td>
                    <td>{formatSignedCurrency(position.unrealizedPnl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="Exposure map" subtitle="Current live concentration by category">
          <div className="bar-stack">
            {exposureRows.map(([category, exposure]) => (
              <div key={category} className="bar-row">
                <div className="bar-row__label">
                  <span>{category}</span>
                  <span>{formatCompactCurrency(exposure)}</span>
                </div>
                <div className="bar-track">
                  <span className="bar-fill" style={{ width: `${(exposure / maxExposure) * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </section>

      <section className="overview-grid overview-grid--dense">
        <Panel title="Health snapshot" subtitle="Critical services that gate execution safety">
          <div className="service-list">
            {criticalServices.map((service) => (
              <article key={service.id} className="service-row">
                <div>
                  <p className="list-row__title">{service.name}</p>
                  <p className="muted">
                    {service.description} · heartbeat {formatRelativeTime(service.lastHeartbeatAt)}
                  </p>
                </div>
                <div className="service-row__meta">
                  <StatusPill
                    tone={
                      service.status === 'healthy'
                        ? 'positive'
                        : service.status === 'degraded'
                          ? 'warning'
                          : 'critical'
                    }
                  >
                    {service.status}
                  </StatusPill>
                  <span>{service.latencyMs} ms</span>
                </div>
              </article>
            ))}
          </div>
        </Panel>

        <Panel title="Desk split" subtitle="Live and paper balances side by side">
          <div className="split-metrics">
            <article className="metric-card">
              <p className="metric-card__label">Live</p>
              <strong>{formatCurrency(liveSummary.availableCapital)}</strong>
              <span>{formatCurrency(liveSummary.liquidationValue)} liquidation value</span>
            </article>
            <article className="metric-card">
              <p className="metric-card__label">Paper</p>
              <strong>{formatCurrency(paperSummary.availableCapital)}</strong>
              <span>{formatCurrency(paperSummary.liquidationValue)} simulated value</span>
            </article>
          </div>
        </Panel>
      </section>
    </div>
  )
}
