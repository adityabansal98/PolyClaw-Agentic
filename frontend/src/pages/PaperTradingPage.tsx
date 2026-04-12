import { useState } from 'react'

import { ConfirmationModal } from '../components/ConfirmationModal'
import { Panel } from '../components/Panel'
import { StatusPill } from '../components/StatusPill'
import { formatCurrency, formatPercent, formatRelativeTime } from '../lib/format'
import type { Opportunity, PortfolioSummary, Position } from '../lib/types'

interface PaperTradingPageProps {
  summary: PortfolioSummary
  opportunities: Opportunity[]
  positions: Position[]
  actionBlockedReason: string | null
  onPromoteOpportunity: (opportunityId: string, stakeOverride: number) => void
}

export function PaperTradingPage({
  summary,
  opportunities,
  positions,
  actionBlockedReason,
  onPromoteOpportunity,
}: PaperTradingPageProps) {
  const [selectedOpportunityId, setSelectedOpportunityId] = useState(opportunities[0]?.id ?? '')
  const [stakeOverride, setStakeOverride] = useState(opportunities[0]?.recommendedStake ?? 0)
  const [confirmPromotion, setConfirmPromotion] = useState(false)

  const selectedOpportunity = opportunities.find((opportunity) => opportunity.id === selectedOpportunityId) ?? null
  const effectiveStakeOverride =
    selectedOpportunity && selectedOpportunity.id !== selectedOpportunityId
      ? selectedOpportunity.recommendedStake
      : stakeOverride

  return (
    <>
      <div className="page-stack">
        <div className="hero-strip">
          <div>
            <p className="eyebrow">Paper Trading</p>
            <h1>Validate ideas before you promote them to live capital</h1>
            <p className="muted">
              Paper routing stays visible as a first-class workflow so the team can test thesis quality before live
              execution.
            </p>
          </div>
        </div>

        <section className="kpi-grid kpi-grid--three">
          <article className="kpi-card">
            <p className="kpi-card__label">Paper total return</p>
            <p className="kpi-card__value">{formatCurrency(summary.totalReturnImmediate)}</p>
            <p className="muted">Return if the simulated book were liquidated now</p>
          </article>
          <article className="kpi-card">
            <p className="kpi-card__label">Paper exposure</p>
            <p className="kpi-card__value">{formatCurrency(summary.openExposure)}</p>
            <p className="muted">{summary.activePositions} simulated positions currently open</p>
          </article>
          <article className="kpi-card">
            <p className="kpi-card__label">Available paper capital</p>
            <p className="kpi-card__value">{formatCurrency(summary.availableCapital)}</p>
            <p className="muted">{summary.pendingApprovals} candidates still in paper-only review</p>
          </article>
        </section>

        <section className="page-with-drawer">
          <div className="page-with-drawer__main">
            <Panel title="Paper-routed opportunities" subtitle="Candidates that should prove themselves before live promotion">
              <div className="table-shell">
                <table className="clickable-table">
                  <thead>
                    <tr>
                      <th>Market</th>
                      <th>Category</th>
                      <th>Expected return</th>
                      <th>Confidence</th>
                      <th>Last review</th>
                    </tr>
                  </thead>
                  <tbody>
                    {opportunities.map((opportunity) => (
                      <tr
                        key={opportunity.id}
                        className={selectedOpportunity?.id === opportunity.id ? 'is-selected' : ''}
                        onClick={() => {
                          setSelectedOpportunityId(opportunity.id)
                          setStakeOverride(opportunity.recommendedStake)
                        }}
                      >
                        <td>{opportunity.question}</td>
                        <td>{opportunity.category}</td>
                        <td>{formatPercent(opportunity.expectedReturn)}</td>
                        <td>{formatPercent(opportunity.confidence)}</td>
                        <td>{formatRelativeTime(opportunity.lastUpdatedAt)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>

            <Panel title="Simulated paper positions" subtitle="Open paper book for strategy validation">
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
                    {positions.map((position) => (
                      <tr key={position.id}>
                        <td>{position.question}</td>
                        <td>{position.category}</td>
                        <td>{formatCurrency(position.stake)}</td>
                        <td>{formatCurrency(position.liquidationValue)}</td>
                        <td>{formatCurrency(position.unrealizedPnl)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          </div>

          <aside className="page-with-drawer__drawer">
            {selectedOpportunity ? (
              <div className="drawer-stack">
                <Panel title="Promotion candidate" subtitle={selectedOpportunity.question}>
                  <div className="detail-grid">
                    <article className="metric-card">
                      <p className="metric-card__label">Expected return</p>
                      <strong>{formatPercent(selectedOpportunity.expectedReturn)}</strong>
                      <span>{formatPercent(selectedOpportunity.edge)} edge</span>
                    </article>
                    <article className="metric-card">
                      <p className="metric-card__label">Paper confidence</p>
                      <strong>{formatPercent(selectedOpportunity.confidence)}</strong>
                      <span>{selectedOpportunity.statusLabel}</span>
                    </article>
                  </div>

                  <div className="copy-block">
                    <p className="copy-block__label">Promotion logic</p>
                    <p>
                      This opportunity can stay in paper until the signal remains stable across multiple refresh windows.
                      Once promoted, it will re-enter the live approval flow with a fresh execution confirmation.
                    </p>
                  </div>

                  <div className="copy-block">
                    <p className="copy-block__label">Current thesis</p>
                    <p>{selectedOpportunity.thesis}</p>
                  </div>

                  <div className="pill-row">
                    <StatusPill tone="warning">Paper-first</StatusPill>
                    <StatusPill tone="info">{selectedOpportunity.category}</StatusPill>
                  </div>

                  {actionBlockedReason ? (
                    <article className="alert-card alert-card--critical">
                      <div>
                        <p className="alert-card__title">Promotion blocked</p>
                        <p className="muted">{actionBlockedReason}</p>
                      </div>
                    </article>
                  ) : null}

                  <label>
                    Live stake on promotion
                    <input
                      type="number"
                      min={0}
                      step={100}
                      value={effectiveStakeOverride}
                      onChange={(event) => setStakeOverride(Number(event.target.value))}
                    />
                  </label>
                  <p className="muted">
                    Suggested live sizing starts at {formatCurrency(selectedOpportunity.recommendedStake)} and can be
                    overridden before promotion.
                  </p>

                  <div className="action-row">
                    <button
                      className="button button--primary"
                      type="button"
                      onClick={() => setConfirmPromotion(true)}
                      disabled={Boolean(actionBlockedReason)}
                    >
                      Promote to live
                    </button>
                  </div>
                </Panel>
              </div>
            ) : (
              <Panel title="Promotion candidate" subtitle="Select a paper-routed opportunity">
                <p className="muted">Choose a row from the paper queue to prepare it for live promotion.</p>
              </Panel>
            )}
          </aside>
        </section>
      </div>

      <ConfirmationModal
        open={confirmPromotion}
        title="Promote this paper trade to the live book?"
        description="This mirrors the paper-tested setup into the live approval path and records the user who promoted it."
        confirmLabel="Promote now"
        disabled={Boolean(actionBlockedReason)}
        onCancel={() => setConfirmPromotion(false)}
        onConfirm={() => {
          if (selectedOpportunity) {
            onPromoteOpportunity(selectedOpportunity.id, effectiveStakeOverride)
          }

          setConfirmPromotion(false)
        }}
      />
    </>
  )
}
