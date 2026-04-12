import { useDeferredValue, useState } from 'react'

import { ConfirmationModal } from '../components/ConfirmationModal'
import { StatusPill } from '../components/StatusPill'
import { formatCurrency, formatPercent, formatRelativeTime, formatSignedCurrency } from '../lib/format'
import type { Position, SessionUser } from '../lib/types'

interface PositionsPageProps {
  positions: Position[]
  sessionUser: SessionUser
  actionBlockedReason: string | null
  pausedCategories: string[]
  onClosePosition: (positionId: string) => void
  onResizePosition: (positionId: string, direction: 'increase' | 'reduce', amount: number) => void
  onMarkReview: (positionId: string) => void
  onPauseCategory: (category: string) => void
  onAddNote: (positionId: string, text: string) => void
}

export function PositionsPage({
  positions,
  sessionUser: _sessionUser,
  actionBlockedReason,
  pausedCategories,
  onClosePosition,
  onResizePosition,
  onMarkReview,
  onPauseCategory,
  onAddNote,
}: PositionsPageProps) {
  const [search, setSearch] = useState('')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [adjustmentAmount, setAdjustmentAmount] = useState(100)
  const [noteDraft, setNoteDraft] = useState('')
  const [modalAction, setModalAction] = useState<{ type: 'close' | 'increase' | 'reduce'; positionId: string } | null>(null)
  const deferredSearch = useDeferredValue(search)

  const filtered = positions.filter((p) => {
    const q = deferredSearch.trim().toLowerCase()
    return !q || p.question.toLowerCase().includes(q) || p.category.toLowerCase().includes(q)
  })

  const expandedPosition = expandedId ? filtered.find((p) => p.id === expandedId) ?? null : null

  function submitNote() {
    if (!expandedPosition || !noteDraft.trim()) return
    onAddNote(expandedPosition.id, noteDraft.trim())
    setNoteDraft('')
  }

  function confirmAction() {
    if (!modalAction) return
    const { type, positionId } = modalAction
    if (type === 'close') onClosePosition(positionId)
    if (type === 'increase') onResizePosition(positionId, 'increase', adjustmentAmount)
    if (type === 'reduce') onResizePosition(positionId, 'reduce', adjustmentAmount)
    setModalAction(null)
  }

  return (
    <>
      <div className="opp-page">
        <div className="opp-page__header">
          <div>
            <h1 className="opp-page__title">Positions</h1>
            <p className="opp-page__subtitle muted">{positions.length} open paper position{positions.length !== 1 ? 's' : ''}</p>
          </div>
          <input
            className="pos-search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search markets…"
          />
        </div>

        {actionBlockedReason ? (
          <div className="opp-blocked-banner">
            <span>⚠ Trading blocked:</span> {actionBlockedReason}
          </div>
        ) : null}

        {filtered.length === 0 ? (
          <p className="muted" style={{ padding: '2rem 0' }}>No open positions yet. Place a paper bet from Opportunities.</p>
        ) : (
          <div className="pos-list">
            {filtered.map((position) => {
              const isExpanded = expandedId === position.id
              const pnlPositive = position.unrealizedPnl >= 0
              const catPaused = pausedCategories.includes(position.category)

              return (
                <article key={position.id} className={`pos-card ${isExpanded ? 'pos-card--expanded' : ''}`}>
                  <button
                    className="pos-card__summary"
                    type="button"
                    onClick={() => setExpandedId(isExpanded ? null : position.id)}
                  >
                    <div className="pos-card__question">{position.question}</div>
                    <div className="pos-card__pills">
                      <StatusPill tone="info">{position.category}</StatusPill>
                      <StatusPill tone={pnlPositive ? 'positive' : 'critical'}>{position.side}</StatusPill>
                      {catPaused ? <StatusPill tone="warning">Paused</StatusPill> : null}
                      {position.status === 'review' ? <StatusPill tone="warning">Review</StatusPill> : null}
                    </div>
                    <div className="pos-card__kpis">
                      <span>
                        <span className="muted">Exposure </span>
                        {formatCurrency(position.stake)}
                      </span>
                      <span>
                        <span className="muted">PnL </span>
                        <span style={{ color: pnlPositive ? '#8bd8be' : '#ffb3ab' }}>
                          {formatSignedCurrency(position.unrealizedPnl)}
                        </span>
                      </span>
                      <span>
                        <span className="muted">Mark </span>
                        {formatPercent(position.currentPrice)}
                      </span>
                    </div>
                    <span className="pos-card__chevron">{isExpanded ? '▲' : '▼'}</span>
                  </button>

                  {isExpanded ? (
                    <div className="pos-card__detail">
                      <div className="pos-detail-grid">
                        <div>
                          <p className="muted" style={{ fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Entry / Mark</p>
                          <strong>{formatPercent(position.entryPrice)} / {formatPercent(position.currentPrice)}</strong>
                          <p className="muted" style={{ fontSize: '0.8rem' }}>Updated {formatRelativeTime(position.updatedAt)}</p>
                        </div>
                        <div>
                          <p className="muted" style={{ fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Shares</p>
                          <strong>{position.shares.toFixed(0)}</strong>
                          <p className="muted" style={{ fontSize: '0.8rem' }}>Liq value {formatCurrency(position.liquidationValue)}</p>
                        </div>
                      </div>

                      <div className="pos-copy-block">
                        <p className="muted" style={{ fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Thesis at entry</p>
                        <p>{position.thesisAtEntry}</p>
                      </div>

                      {actionBlockedReason ? null : (
                        <div className="pos-actions">
                          <label className="pos-adj-label">
                            Adj. amount ($)
                            <input
                              type="number"
                              min={50}
                              step={50}
                              value={adjustmentAmount}
                              onChange={(e) => setAdjustmentAmount(Number(e.target.value))}
                            />
                          </label>
                          <div className="action-row">
                            <button
                              className="button button--ghost"
                              type="button"
                              onClick={() => setModalAction({ type: 'increase', positionId: position.id })}
                            >
                              Increase
                            </button>
                            <button
                              className="button button--ghost"
                              type="button"
                              onClick={() => setModalAction({ type: 'reduce', positionId: position.id })}
                            >
                              Reduce
                            </button>
                            <button
                              className="button button--danger"
                              type="button"
                              onClick={() => setModalAction({ type: 'close', positionId: position.id })}
                            >
                              Close
                            </button>
                          </div>
                          <div className="action-row">
                            <button
                              className="button button--ghost"
                              type="button"
                              onClick={() => onMarkReview(position.id)}
                            >
                              Flag for review
                            </button>
                            <button
                              className="button button--ghost"
                              type="button"
                              onClick={() => onPauseCategory(position.category)}
                              disabled={catPaused}
                            >
                              Pause {position.category}
                            </button>
                          </div>
                        </div>
                      )}

                      {position.notes.length > 0 ? (
                        <div className="pos-notes">
                          {position.notes.map((note) => (
                            <div key={note.id} className="pos-note">
                              <span className="pos-note__author">{note.author}</span>
                              <span className="muted" style={{ fontSize: '0.78rem' }}>{formatRelativeTime(note.createdAt)}</span>
                              <p style={{ margin: '0.25rem 0 0' }}>{note.text}</p>
                            </div>
                          ))}
                        </div>
                      ) : null}

                      <label style={{ fontSize: '0.85rem', color: 'var(--text-soft)' }}>
                        Add note
                        <textarea
                          value={noteDraft}
                          onChange={(e) => setNoteDraft(e.target.value)}
                          placeholder="Exit notes, thesis update…"
                          style={{ minHeight: '4rem' }}
                        />
                      </label>
                      <button className="button button--ghost" type="button" onClick={submitNote} style={{ alignSelf: 'flex-start' }}>
                        Save note
                      </button>
                    </div>
                  ) : null}
                </article>
              )
            })}
          </div>
        )}
      </div>

      <ConfirmationModal
        open={modalAction !== null}
        title={
          modalAction?.type === 'close'
            ? 'Close this paper position?'
            : modalAction?.type === 'increase'
              ? 'Increase paper position?'
              : 'Reduce paper position?'
        }
        description={
          modalAction?.type === 'close'
            ? 'This sends a paper sell order to fully close the position.'
            : `Change position size by ${formatCurrency(adjustmentAmount)}.`
        }
        confirmLabel={modalAction?.type === 'close' ? 'Confirm close' : 'Confirm'}
        confirmTone={modalAction?.type === 'close' ? 'danger' : 'primary'}
        disabled={Boolean(actionBlockedReason)}
        onCancel={() => setModalAction(null)}
        onConfirm={confirmAction}
      />
    </>
  )
}
