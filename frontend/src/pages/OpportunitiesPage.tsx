import { useState } from 'react'

import { ConfirmationModal } from '../components/ConfirmationModal'
import type { ScoredOpportunity, OpportunitySide } from '../lib/types'

const CATEGORIES = ['All', 'NBA', 'Soccer', 'Cricket', 'Elections', 'Mentions']
type SortKey = 'score' | 'edge_pct' | 'liquidity_score'

interface OpportunitiesPageProps {
  scoredOpportunities: ScoredOpportunity[]
  scoredLoading: boolean
  paperActionBlockedReason: string | null
  onPlaceBet: (marketId: string, side: OpportunitySide, size: number) => Promise<void>
}

function ScoreBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = pct >= 70 ? '#61d5ab' : pct >= 50 ? '#f3b54b' : '#a1a1aa'
  return (
    <div className="score-bar-track">
      <div className="score-bar-fill" style={{ width: `${pct}%`, background: color }} />
    </div>
  )
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
  const [category, setCategory] = useState('All')
  const [sortBy, setSortBy] = useState<SortKey>('score')
  const [pendingBet, setPendingBet] = useState<{ pick: ScoredOpportunity; size: number } | null>(null)
  const [betSize, setBetSize] = useState(100)
  const [skippedIds, setSkippedIds] = useState<Set<string>>(new Set())
  const [bettingId, setBettingId] = useState<string | null>(null)

  const filtered = scoredOpportunities
    .filter((p) => !skippedIds.has(p.market_id))
    .filter((p) => category === 'All' || p.category === category)
    .sort((a, b) => (b[sortBy] ?? 0) - (a[sortBy] ?? 0))

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
                ? 'Running scoring pipeline…'
                : `${filtered.length} scored picks · refreshes every 60s`}
            </p>
          </div>
          <div className="opp-page__controls">
            <div className="cat-strip">
              {CATEGORIES.map((cat) => (
                <button
                  key={cat}
                  className={`cat-chip ${category === cat ? 'cat-chip--active' : ''}`}
                  type="button"
                  onClick={() => setCategory(cat)}
                >
                  {cat}
                </button>
              ))}
            </div>
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
            <span>⚠ Paper trading blocked:</span> {paperActionBlockedReason}
          </div>
        ) : null}

        <div className="opp-card-list">
          {scoredLoading && scoredOpportunities.length === 0 ? (
            Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)
          ) : filtered.length === 0 ? (
            <p className="muted" style={{ gridColumn: '1 / -1', padding: '2rem 0' }}>
              No picks available for this category yet.
            </p>
          ) : (
            filtered.map((pick) => (
              <article key={pick.market_id} className="opp-card">
                <div className="opp-card__top">
                  <div className="opp-card__meta">
                    <span className="opp-card__category">{pick.category}</span>
                    <SideBadge side={pick.side} />
                  </div>
                  {pick.market_url ? (
                    <a
                      href={pick.market_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="opp-card__ext-link"
                    >
                      ↗
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
                    <span className="opp-metric__label">Score</span>
                    <div className="opp-metric__score-row">
                      <strong className="opp-metric__value">{pick.score_pct.toFixed(0)}</strong>
                      <ScoreBar value={pick.score} />
                    </div>
                  </div>
                  <div className="opp-metric">
                    <span className="opp-metric__label">Confidence</span>
                    <strong className="opp-metric__value">{pick.confidence_pct.toFixed(0)}%</strong>
                  </div>
                </div>

                {pick.rationale_tags.length > 0 ? (
                  <div className="opp-card__tags">
                    {pick.rationale_tags.map((tag) => (
                      <span key={tag} className="opp-tag">
                        {tag}
                      </span>
                    ))}
                  </div>
                ) : null}

                {pick.ai_commentary ? (
                  <p className="opp-card__commentary">{pick.ai_commentary}</p>
                ) : null}

                <div className="opp-card__footer">
                  <span className="muted" style={{ fontSize: '0.8rem' }}>
                    Liq {(pick.liquidity_score * 100).toFixed(0)} ·{' '}
                    {pick.hours_to_resolution != null
                      ? `${Math.round(pick.hours_to_resolution)}h left`
                      : 'No expiry'}
                  </span>
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
                      {bettingId === pick.market_id ? 'Placing…' : 'Bet on Paper'}
                    </button>
                  </div>
                </div>
              </article>
            ))
          )}
        </div>
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
