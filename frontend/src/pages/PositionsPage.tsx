import { useDeferredValue, useState } from 'react'

import { ConfirmationModal } from '../components/ConfirmationModal'
import { Panel } from '../components/Panel'
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
  sessionUser,
  actionBlockedReason,
  pausedCategories,
  onClosePosition,
  onResizePosition,
  onMarkReview,
  onPauseCategory,
  onAddNote,
}: PositionsPageProps) {
  const [selectedPositionId, setSelectedPositionId] = useState(positions[0]?.id ?? '')
  const [search, setSearch] = useState('')
  const [adjustmentAmount, setAdjustmentAmount] = useState(1000)
  const [noteDraft, setNoteDraft] = useState('')
  const [modalAction, setModalAction] = useState<'close' | 'increase' | 'reduce' | null>(null)
  const deferredSearch = useDeferredValue(search)

  const filtered = positions.filter((position) => {
    const query = deferredSearch.trim().toLowerCase()
    if (!query) {
      return true
    }

    return (
      position.question.toLowerCase().includes(query) ||
      position.category.toLowerCase().includes(query) ||
      position.status.toLowerCase().includes(query)
    )
  })

  const selectedPosition = filtered.find((position) => position.id === selectedPositionId) ?? filtered[0] ?? null
  const categoryPaused = selectedPosition ? pausedCategories.includes(selectedPosition.category) : false

  function confirmAction() {
    if (!selectedPosition) {
      return
    }

    if (modalAction === 'close') {
      onClosePosition(selectedPosition.id)
    }

    if (modalAction === 'increase') {
      onResizePosition(selectedPosition.id, 'increase', adjustmentAmount)
    }

    if (modalAction === 'reduce') {
      onResizePosition(selectedPosition.id, 'reduce', adjustmentAmount)
    }

    setModalAction(null)
  }

  function submitNote() {
    if (!selectedPosition || !noteDraft.trim()) {
      return
    }

    onAddNote(selectedPosition.id, noteDraft.trim())
    setNoteDraft('')
  }

  return (
    <>
      <div className="page-stack">
        <div className="hero-strip">
          <div>
            <p className="eyebrow">Positions</p>
            <h1>Monitor paper-backed bets, update sizing, and manage category risk</h1>
            <p className="muted">
              Phase 1 keeps the current book paper-backed while live holdings remain unavailable. You can still resize,
              close, review, and pause categories from here.
            </p>
          </div>
        </div>

        <section className="page-with-drawer">
          <div className="page-with-drawer__main">
            <Panel title="Open paper positions" subtitle="Current paper-backed exposure and mark-to-market">
              <div className="filter-bar">
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search market or category"
                />
              </div>
              <div className="table-shell">
                <table className="clickable-table">
                  <thead>
                    <tr>
                      <th>Market</th>
                      <th>Category</th>
                      <th>Status</th>
                      <th>Exposure</th>
                      <th>Liquidation</th>
                      <th>Unrealized</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((position) => (
                      <tr
                        key={position.id}
                        className={selectedPosition?.id === position.id ? 'is-selected' : ''}
                        onClick={() => setSelectedPositionId(position.id)}
                      >
                        <td>{position.question}</td>
                        <td>{position.category}</td>
                        <td>{position.status}</td>
                        <td>{formatCurrency(position.stake)}</td>
                        <td>{formatCurrency(position.liquidationValue)}</td>
                        <td>{formatSignedCurrency(position.unrealizedPnl)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          </div>

          <aside className="page-with-drawer__drawer">
            {selectedPosition ? (
              <div className="drawer-stack">
                <Panel title="Position detail" subtitle={selectedPosition.question}>
                  <div className="detail-grid">
                    <article className="metric-card">
                      <p className="metric-card__label">Exposure</p>
                      <strong>{formatCurrency(selectedPosition.stake)}</strong>
                      <span>{formatCurrency(selectedPosition.liquidationValue)} liquidation value</span>
                    </article>
                    <article className="metric-card">
                      <p className="metric-card__label">Unrealized PnL</p>
                      <strong>{formatSignedCurrency(selectedPosition.unrealizedPnl)}</strong>
                      <span>{selectedPosition.shares.toFixed(0)} shares</span>
                    </article>
                    <article className="metric-card">
                      <p className="metric-card__label">Entry vs mark</p>
                      <strong>
                        {formatPercent(selectedPosition.entryPrice)} / {formatPercent(selectedPosition.currentPrice)}
                      </strong>
                      <span>Updated {formatRelativeTime(selectedPosition.updatedAt)}</span>
                    </article>
                  </div>

                  <div className="pill-row">
                    <StatusPill tone="info">{selectedPosition.category}</StatusPill>
                    <StatusPill tone="neutral">{selectedPosition.marketType}</StatusPill>
                    <StatusPill tone={selectedPosition.unrealizedPnl >= 0 ? 'positive' : 'critical'}>
                      {selectedPosition.side}
                    </StatusPill>
                    {categoryPaused ? <StatusPill tone="warning">Category paused</StatusPill> : null}
                  </div>

                  <div className="copy-block">
                    <p className="copy-block__label">Thesis at entry</p>
                    <p>{selectedPosition.thesisAtEntry}</p>
                  </div>
                  <div className="copy-block">
                    <p className="copy-block__label">Current model view</p>
                    <p>{selectedPosition.modelView}</p>
                  </div>
                  <div className="copy-block">
                    <p className="copy-block__label">Exit guidance</p>
                    <p>{selectedPosition.exitGuidance}</p>
                  </div>

                  {actionBlockedReason ? (
                    <article className="alert-card alert-card--critical">
                      <div>
                        <p className="alert-card__title">Paper execution blocked</p>
                        <p className="muted">{actionBlockedReason}</p>
                      </div>
                    </article>
                  ) : null}

                  <label>
                    Adjustment amount
                    <input
                      type="number"
                      min={100}
                      step={100}
                      value={adjustmentAmount}
                      onChange={(event) => setAdjustmentAmount(Number(event.target.value))}
                    />
                  </label>

                  <div className="action-row">
                    <button
                      className="button button--ghost"
                      type="button"
                      onClick={() => setModalAction('increase')}
                      disabled={Boolean(actionBlockedReason)}
                    >
                      Increase size
                    </button>
                    <button
                      className="button button--ghost"
                      type="button"
                      onClick={() => setModalAction('reduce')}
                      disabled={Boolean(actionBlockedReason)}
                    >
                      Reduce size
                    </button>
                    <button
                      className="button button--danger"
                      type="button"
                      onClick={() => setModalAction('close')}
                      disabled={Boolean(actionBlockedReason)}
                    >
                      Close paper position
                    </button>
                  </div>

                  <div className="action-row">
                    <button className="button button--ghost" type="button" onClick={() => onMarkReview(selectedPosition.id)}>
                      Mark for review
                    </button>
                    <button className="button button--ghost" type="button" onClick={() => onPauseCategory(selectedPosition.category)}>
                      Pause similar markets
                    </button>
                  </div>
                </Panel>

                <Panel title="Position notes" subtitle={`Desk notes by ${sessionUser.name}`}>
                  <div className="note-stack">
                    {selectedPosition.notes.map((item) => (
                      <article key={item.id} className="note-card">
                        <div className="note-card__header">
                          <strong>{item.author}</strong>
                          <span>{formatRelativeTime(item.createdAt)}</span>
                        </div>
                        <p>{item.text}</p>
                      </article>
                    ))}
                  </div>
                  <label>
                    Add note
                    <textarea
                      value={noteDraft}
                      onChange={(event) => setNoteDraft(event.target.value)}
                      placeholder="Capture follow-up actions, exit notes, or size decisions."
                    />
                  </label>
                  <button className="button button--ghost" type="button" onClick={submitNote}>
                    Save note
                  </button>
                </Panel>
              </div>
            ) : (
              <Panel title="Position detail" subtitle="Select a paper-backed position to inspect it">
                <p className="muted">No current positions match the search.</p>
              </Panel>
            )}
          </aside>
        </section>
      </div>

      <ConfirmationModal
        open={modalAction !== null}
        title={
          modalAction === 'close'
            ? 'Close this paper position?'
            : modalAction === 'increase'
              ? 'Increase this paper position?'
              : 'Reduce this paper position?'
        }
        description={
          modalAction === 'close'
            ? 'This sends a paper sell order to the backend to close the position.'
            : modalAction === 'increase'
              ? `Add ${formatCurrency(adjustmentAmount)} of paper notional exposure to this position.`
              : `Reduce ${formatCurrency(adjustmentAmount)} of paper notional exposure from this position.`
        }
        confirmLabel={modalAction === 'close' ? 'Confirm close' : 'Confirm change'}
        confirmTone={modalAction === 'close' ? 'danger' : 'primary'}
        disabled={Boolean(actionBlockedReason)}
        onCancel={() => setModalAction(null)}
        onConfirm={confirmAction}
      />
    </>
  )
}
