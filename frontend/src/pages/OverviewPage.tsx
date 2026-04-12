import {
  formatCompactCurrency,
  formatCurrency,
  formatRelativeTime,
  formatSignedCurrency,
} from '../lib/format'
import type { AlertItem, FreshnessEntry, Opportunity, PortfolioSummary, Position, ServiceHealth } from '../lib/types'
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
  liveHoldingsAvailable: boolean
  freshness: {
    opportunities: FreshnessEntry
    portfolio: FreshnessEntry
    positions: FreshnessEntry
  }
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
  liveHoldingsAvailable,
  freshness,
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
          <h1>Live market feed plus paper-backed portfolio control</h1>
          <p className="muted">
            Auto-refresh is on. Last full refresh {formatRelativeTime(lastRefreshAt)}. Live opportunities come from
            Polymarket now, while current holdings stay paper-backed in Phase 1.
          </p>
        </div>
        <div className="hero-strip__actions">
          <button className="button button--ghost" type="button" onClick={() => onNavigate('opportunities')}>
            Review opportunities
          </button>
          <button className="button button--primary" type="button" onClick={() => onNavigate('positions')}>
            Inspect current positions
          </button>
        </div>
      </div>

      <section className="kpi-grid">
        <KpiCard
          label="Total return if liquidated now"
          value={formatCurrency(paperSummary.totalReturnImmediate)}
          delta={formatSignedCurrency(paperSummary.dailyPnl)}
          helper="Paper-backed current book"
          trend={positions.slice(0, 3).flatMap((position) => position.priceHistory.slice(-2)).slice(-6)}
          tone="amber"
          emphasis
        />
        <KpiCard
          label="Open exposure"
          value={formatCurrency(paperSummary.openExposure)}
          delta={`${paperSummary.activePositions} paper-backed positions`}
          helper="Committed current notional"
          trend={positions.map((position) => position.stake / 10000).slice(-6)}
          tone="blue"
        />
        <KpiCard
          label="Available capital"
          value={formatCurrency(paperSummary.availableCapital)}
          delta={`${paperSummary.activePositions} active positions`}
          helper="Cash available for new paper trades"
          trend={[
            (paperSummary.availableCapital ?? 0) / 100000,
            ((paperSummary.availableCapital ?? 0) - 1800) / 100000,
            (paperSummary.availableCapital ?? 0) / 100000,
          ]}
          tone="teal"
        />
        <KpiCard
          label="Live holdings"
          value={liveHoldingsAvailable ? formatCurrency(liveSummary.openExposure) : 'Unavailable'}
          delta={liveHoldingsAvailable ? `${liveSummary.activePositions} live positions` : 'Phase 2'}
          helper="Real live account reading lands after Data API integration"
          trend={opportunities.slice(0, 3).flatMap((opportunity) => opportunity.priceHistory.slice(-2)).slice(-6)}
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
          subtitle="Highest-volume categorized live markets requiring review"
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
                  <span>{formatCompactCurrency(opportunity.liquidity)}</span>
                </div>
              </article>
            ))}
          </div>
        </Panel>
      </section>

      <section className="overview-grid overview-grid--dense">
        <Panel
          title="Current positions"
          subtitle="Paper-backed existing book with current mark-to-market"
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

        <Panel title="Exposure map" subtitle="Current paper-backed concentration by category">
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
        <Panel title="Health snapshot" subtitle="Backend freshness and execution safety gates">
          <div className="split-metrics">
            <article className="metric-card">
              <p className="metric-card__label">Opportunities</p>
              <strong>{freshness.opportunities.stale ? 'Stale' : 'Fresh'}</strong>
              <span>
                {freshness.opportunities.updatedAt
                  ? `Updated ${formatRelativeTime(freshness.opportunities.updatedAt)}`
                  : 'Awaiting first sync'}
              </span>
            </article>
            <article className="metric-card">
              <p className="metric-card__label">Portfolio</p>
              <strong>{freshness.portfolio.stale ? 'Stale' : 'Fresh'}</strong>
              <span>
                {freshness.portfolio.updatedAt
                  ? `Updated ${formatRelativeTime(freshness.portfolio.updatedAt)}`
                  : 'Awaiting first sync'}
              </span>
            </article>
            <article className="metric-card">
              <p className="metric-card__label">Positions</p>
              <strong>{freshness.positions.stale ? 'Stale' : 'Fresh'}</strong>
              <span>
                {freshness.positions.updatedAt
                  ? `Updated ${formatRelativeTime(freshness.positions.updatedAt)}`
                  : 'Awaiting first sync'}
              </span>
            </article>
          </div>

          <div className="service-list">
            {criticalServices.map((service) => (
              <article key={service.id} className="service-row">
                <div>
                  <p className="list-row__title">{service.name}</p>
                  <p className="muted">
                    {service.description} · heartbeat{' '}
                    {service.lastHeartbeatAt ? formatRelativeTime(service.lastHeartbeatAt) : 'Awaiting first sync'}
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

        <Panel title="Desk split" subtitle="What is real now versus what arrives in Phase 2">
          <div className="split-metrics">
            <article className="metric-card">
              <p className="metric-card__label">Live feed</p>
              <strong>{opportunities.length}</strong>
              <span>Categorized opportunities available for review</span>
            </article>
            <article className="metric-card">
              <p className="metric-card__label">Paper portfolio</p>
              <strong>{formatCurrency(paperSummary.availableCapital)}</strong>
              <span>{formatCurrency(paperSummary.liquidationValue)} simulated value</span>
            </article>
          </div>
        </Panel>
      </section>
    </div>
  )
}
