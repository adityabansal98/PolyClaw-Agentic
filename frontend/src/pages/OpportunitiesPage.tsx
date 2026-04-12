import { useState } from 'react'

import { ConfirmationModal } from '../components/ConfirmationModal'
import type { ScoredOpportunity, OpportunitySide } from '../lib/types'

const CATEGORIES = ['NBA', 'Soccer', 'Cricket', 'Elections', 'Mentions'] as const
type SortKey = 'score' | 'edge_pct' | 'liquidity_score'

interface OpportunitiesPageProps {
  scoredOpportunities: ScoredOpportunity[]
  scoredLoading: boolean
  paperActionBlockedReason: string | null
  onPlaceBet: (marketId: string, side: OpportunitySide, size: number) => Promise<void>
}

function SideBadge({ side }: { side: OpportunitySide }) {
  return (
    <span className={`side-badge side-badge--${side.toLowerCase()}`}>{side}</span>
  )
}

function SkeletonCard() {
  return (
    <article className="opp-card opp-card--skeleton">
      <div className="opp-card__skeleton-line opp-card__skeleton-line--wide" />
      <div className="opp-card__skeleton-line opp-card__skeleton-line--medium" />
      <div className="opp-card__skeleton-line opp-card__skeleton-line--narrow" />
    </article>
  )
}

export function OpportunitiesPage({
  scoredOpportunities,
  scoredLoading,
  paperActionBlockedReason,
  onPlaceBet,
}: OpportunitiesPageProps) {
  const [sortBy, setSortBy] = useState<SortKey>('score')
  const [pendingBet, setPendingBet] = useState<{ pick: ScoredOpportunity; size: number } | null>(null)
  const [betSize, setBetSize] = useState(100)
  const [skippedIds, setSkippedIds] = useState<Set<string>>(new Set())
  const [bettingId, setBettingId] = useState<string | null>(null)

  const picksByCategory = new Map<string, ScoredOpportunity[]>()
  for (const cat of CATEGORIES) {
    const picks = scoredOpportunities
      .filter((p) => p.category === cat && !skippedIds.has(p.market_id))
      .sort((a, b) => (b[sortBy] ?? 0) - (a[sortBy] ?? 0))
    picksByCategory.set(cat, picks)
  }

  async function handleConfirmBet() {
    if (!pendingBet) return
    const { pick, size } = pendingBet
    setBettingId(pick.market_id)
    setPendingBet(null)
    try {
      await onPlaceBet(pick.market_id, pick.side, size)
    } finally {
      setBettingId(null)
    }
  }

  return (
    <>
      <div className="opp-page">
        <div className="opp-page__header">
          <div>
            <h1 className="opp-page__title">Trading Opportunities</h1>
            <p className="opp-page__subtitle muted">
              {scoredLoading && scoredOpportunities.length === 0
                ? 'Running scoring pipeline...'
                : `Top 5 picks per category · refreshes every 30s`}
            </p>
          </div>
          <div className="opp-page__controls">
            <select
              className="opp-sort-select"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortKey)}
            >
              <option value="score">Sort: Score</option>
              <option value="edge_pct">Sort: Edge %</option>
              <option value="liquidity_score">Sort: Liquidity</option>
            </select>
          </div>
        </div>

        {paperActionBlockedReason ? (
          <div className="opp-blocked-banner">
            <span>Warning: Paper trading blocked:</span> {paperActionBlockedReason}
          </div>
        ) : null}

        {scoredLoading && scoredOpportunities.length === 0 ? (
          <div className="opp-categories">
            {CATEGORIES.map((cat) => (
              <section key={cat} className="opp-category-section">
                <h2 className="opp-category-section__title">{cat}</h2>
                <div className="opp-category-section__cards">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <SkeletonCard key={i} />
                  ))}
                </div>
              </section>
            ))}
          </div>
        ) : (
          <div className="opp-categories">
            {CATEGORIES.map((cat) => {
              const picks = picksByCategory.get(cat) ?? []
              return (
                <section key={cat} className="opp-category-section">
                  <h2 className="opp-category-section__title">
                    {cat}
                    <span className="opp-category-section__count">{picks.length}</span>
                  </h2>
                  {picks.length === 0 ? (
                    <p className="muted" style={{ fontSize: '0.85rem', padding: '0.5rem 0' }}>
                      No picks available yet.
                    </p>
                  ) : (
                    <div className="opp-category-section__cards">
                      {picks.map((pick) => (
                        <article key={pick.market_id} className="opp-card">
                          <div className="opp-card__top">
                            <div className="opp-card__meta">
                              <SideBadge side={pick.side} />
                            </div>
                            {pick.market_url ? (
                              <a
                                href={pick.market_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="opp-card__ext-link"
                              >
                                ->
                              </a>
                            ) : null}
                          </div>

                          <p className="opp-card__question">{pick.question}</p>

                          <div className="opp-card__metrics">
                            <div className="opp-metric">
                              <span className="opp-metric__label">Edge</span>
                              <strong className="opp-metric__value opp-metric__value--edge">
                                +{pick.edge_pct.toFixed(1)}%
                              </strong>
                            </div>
                            <div className="opp-metric">
                              <span className="opp-metric__label">Our View</span>
                              <strong className="opp-metric__value">
                                {(pick.p_model_yes * 100).toFixed(1)}%
                              </strong>
                            </div>
                            <div className="opp-metric">
                              <span className="opp-metric__label">Market</span>
                              <strong className="opp-metric__value">
                                {(pick.p_market_yes * 100).toFixed(1)}%
                              </strong>
                            </div>
                          </div>

                          {pick.ai_commentary ? (
                            <p className="opp-card__commentary">{pick.ai_commentary}</p>
                          ) : null}

                          <div className="opp-card__footer">
                            <div className="opp-card__actions">
                              <button
                                className="button button--ghost opp-card__skip"
                                type="button"
                                onClick={() => setSkippedIds((prev) => new Set([...prev, pick.market_id]))}
                              >
                                Skip
                              </button>
                              <button
                                className="button button--primary"
                                type="button"
                                disabled={Boolean(paperActionBlockedReason) || bettingId === pick.market_id}
                                onClick={() => setPendingBet({ pick, size: betSize })}
                              >
                                {bettingId === pick.market_id ? 'Placing...' : 'Bet on Paper'}
                              </button>
                            </div>
                          </div>
                        </article>
                      ))}
                    </div>
                  )}
                </section>
              )
            })}
          </div>
        )}
      </div>

      <ConfirmationModal
        open={pendingBet !== null}
        title={`Paper bet: ${pendingBet?.pick.side} on this market?`}
        description={
          pendingBet
            ? `Submit a $${pendingBet.size} paper trade on ${pendingBet.pick.question}. Edge: +${pendingBet.pick.edge_pct.toFixed(1)}%.`
            : ''
        }
        confirmLabel="Submit paper bet"
        confirmTone="primary"
        disabled={Boolean(paperActionBlockedReason)}
        onCancel={() => setPendingBet(null)}
        onConfirm={handleConfirmBet}
      >
        <label style={{ marginTop: '0.5rem' }}>
          Stake ($)
          <input
            type="number"
            min={50}
            max={5000}
            step={50}
            value={betSize}
            onChange={(e) => setBetSize(Number(e.target.value))}
          />
        </label>
      </ConfirmationModal>
    </>
  )
}
