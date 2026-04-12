import { useDeferredValue, useState } from 'react'

import { ConfirmationModal } from '../components/ConfirmationModal'
import { Panel } from '../components/Panel'
import { StatusPill } from '../components/StatusPill'
import { formatCompactCurrency, formatCurrency, formatPercent, formatRelativeTime } from '../lib/format'
import type { Opportunity, SessionUser } from '../lib/types'

type RankMetric = 'expectedReturn' | 'confidence' | 'urgencyScore' | 'liquidity'

interface OpportunitiesPageProps {
  opportunities: Opportunity[]
  sessionUser: SessionUser
  actionBlockedReason: string | null
  pausedCategories: string[]
  onApproveLive: (opportunityId: string, stakeOverride: number) => void
  onSendToPaper: (opportunityId: string, stakeOverride: number) => void
  onReject: (opportunityId: string) => void
  onAddNote: (opportunityId: string, text: string) => void
  onAddLink: (opportunityId: string, title: string, url: string) => void
  onAddFile: (opportunityId: string, file: File) => void
}

export function OpportunitiesPage({
  opportunities,
  sessionUser,
  actionBlockedReason,
  pausedCategories,
  onApproveLive,
  onSendToPaper,
  onReject,
  onAddNote,
  onAddLink,
  onAddFile,
}: OpportunitiesPageProps) {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('All')
  const [status, setStatus] = useState('All')
  const [rankBy, setRankBy] = useState<RankMetric>('expectedReturn')
  const [selectedOpportunityId, setSelectedOpportunityId] = useState(opportunities[0]?.id ?? '')
  const [stakeOverride, setStakeOverride] = useState<number>(opportunities[0]?.recommendedStake ?? 0)
  const [noteDraft, setNoteDraft] = useState('')
  const [linkTitle, setLinkTitle] = useState('')
  const [linkUrl, setLinkUrl] = useState('')
  const [modalAction, setModalAction] = useState<'live' | 'paper' | 'reject' | null>(null)

  const deferredSearch = useDeferredValue(search)
  const categories = ['All', ...new Set(opportunities.map((opportunity) => opportunity.category))]
  const statuses = ['All', ...new Set(opportunities.map((opportunity) => opportunity.currentStage))]

  const filtered = opportunities
    .filter((opportunity) => category === 'All' || opportunity.category === category)
    .filter((opportunity) => status === 'All' || opportunity.currentStage === status)
    .filter((opportunity) => {
      const query = deferredSearch.trim().toLowerCase()
      if (!query) {
        return true
      }

      return (
        opportunity.question.toLowerCase().includes(query) ||
        opportunity.category.toLowerCase().includes(query) ||
        opportunity.tags.join(' ').toLowerCase().includes(query)
      )
    })
    .sort((left, right) => right[rankBy] - left[rankBy])

  const selectedOpportunity = filtered.find((opportunity) => opportunity.id === selectedOpportunityId) ?? filtered[0] ?? null
  const effectiveStakeOverride =
    selectedOpportunity && selectedOpportunity.id !== selectedOpportunityId
      ? selectedOpportunity.recommendedStake
      : stakeOverride
  const categoryPaused = selectedOpportunity ? pausedCategories.includes(selectedOpportunity.category) : false
  const blockedReason =
    actionBlockedReason ?? (categoryPaused ? `${selectedOpportunity?.category} approvals are paused right now.` : null)

  function submitNote() {
    if (!selectedOpportunity || !noteDraft.trim()) {
      return
    }

    onAddNote(selectedOpportunity.id, noteDraft.trim())
    setNoteDraft('')
  }

  function submitLink() {
    if (!selectedOpportunity || !linkTitle.trim() || !linkUrl.trim()) {
      return
    }

    onAddLink(selectedOpportunity.id, linkTitle.trim(), linkUrl.trim())
    setLinkTitle('')
    setLinkUrl('')
  }

  function submitFile(event: React.ChangeEvent<HTMLInputElement>) {
    if (!selectedOpportunity || !event.target.files?.[0]) {
      return
    }

    onAddFile(selectedOpportunity.id, event.target.files[0])
    event.target.value = ''
  }

  function confirmAction() {
    if (!selectedOpportunity) {
      return
    }

    if (modalAction === 'live') {
      onApproveLive(selectedOpportunity.id, effectiveStakeOverride)
    }

    if (modalAction === 'paper') {
      onSendToPaper(selectedOpportunity.id, effectiveStakeOverride)
    }

    if (modalAction === 'reject') {
      onReject(selectedOpportunity.id)
    }

    setModalAction(null)
  }

  return (
    <>
      <div className="page-stack">
        <div className="hero-strip">
          <div>
            <p className="eyebrow">Opportunities</p>
            <h1>Review candidate bets before capital is committed</h1>
            <p className="muted">
              Sort by expected return, confidence, urgency, or liquidity. Every approval still requires one extra
              execution confirmation.
            </p>
          </div>
        </div>

        <section className="page-with-drawer">
          <div className="page-with-drawer__main">
            <Panel title="Candidate queue" subtitle="Full table of live and paper-routed opportunities">
              <div className="filter-bar">
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search market, category, or tag"
                />
                <select value={category} onChange={(event) => setCategory(event.target.value)}>
                  {categories.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
                <select value={status} onChange={(event) => setStatus(event.target.value)}>
                  {statuses.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </div>

              <div className="segment-control">
                {([
                  ['expectedReturn', 'Expected return'],
                  ['confidence', 'Confidence'],
                  ['urgencyScore', 'Urgency'],
                  ['liquidity', 'Liquidity'],
                ] as const).map(([value, label]) => (
                  <button
                    key={value}
                    className={`segment-control__button ${rankBy === value ? 'is-active' : ''}`}
                    type="button"
                    onClick={() => setRankBy(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>

              <div className="table-shell">
                <table className="clickable-table">
                  <thead>
                    <tr>
                      <th>Market</th>
                      <th>Category</th>
                      <th>Stage</th>
                      <th>EV</th>
                      <th>Confidence</th>
                      <th>Rec. stake</th>
                      <th>Last refresh</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((opportunity) => (
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
                        <td>{opportunity.statusLabel}</td>
                        <td>{formatPercent(opportunity.expectedReturn)}</td>
                        <td>{formatPercent(opportunity.confidence)}</td>
                        <td>{formatCurrency(opportunity.recommendedStake)}</td>
                        <td>{formatRelativeTime(opportunity.lastUpdatedAt)}</td>
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
                <Panel title="Opportunity detail" subtitle={selectedOpportunity.question}>
                  <div className="detail-grid">
                    <article className="metric-card">
                      <p className="metric-card__label">Expected return</p>
                      <strong>{formatPercent(selectedOpportunity.expectedReturn)}</strong>
                      <span>Edge {formatPercent(selectedOpportunity.edge)}</span>
                    </article>
                    <article className="metric-card">
                      <p className="metric-card__label">Confidence</p>
                      <strong>{formatPercent(selectedOpportunity.confidence)}</strong>
                      <span>Signal {formatPercent(selectedOpportunity.signalStrength)}</span>
                    </article>
                    <article className="metric-card">
                      <p className="metric-card__label">Market vs model</p>
                      <strong>
                        {formatPercent(selectedOpportunity.marketProbability)} /{' '}
                        {formatPercent(selectedOpportunity.modelProbability)}
                      </strong>
                      <span>Spread {selectedOpportunity.spreadBps} bps</span>
                    </article>
                    <article className="metric-card">
                      <p className="metric-card__label">Liquidity</p>
                      <strong>{formatCompactCurrency(selectedOpportunity.liquidity)}</strong>
                      <span>Depth {formatCompactCurrency(selectedOpportunity.marketDepth)}</span>
                    </article>
                  </div>

                  <div className="pill-row">
                    <StatusPill tone="info">{selectedOpportunity.category}</StatusPill>
                    <StatusPill tone="neutral">{selectedOpportunity.marketType}</StatusPill>
                    <StatusPill tone={selectedOpportunity.currentStage === 'rejected' ? 'critical' : 'positive'}>
                      {selectedOpportunity.side}
                    </StatusPill>
                  </div>

                  <div className="copy-block">
                    <p className="copy-block__label">Strategy summary</p>
                    <p>{selectedOpportunity.strategySummary}</p>
                  </div>
                  <div className="copy-block">
                    <p className="copy-block__label">Why the model likes this bet</p>
                    <p>{selectedOpportunity.thesis}</p>
                  </div>
                  <div className="copy-block">
                    <p className="copy-block__label">Invalidation</p>
                    <p>{selectedOpportunity.invalidation}</p>
                  </div>

                  <ul className="tag-list">
                    {selectedOpportunity.riskFlags.map((flag) => (
                      <li key={flag}>{flag}</li>
                    ))}
                  </ul>

                  {selectedOpportunity.correlationWarning ? (
                    <article className="alert-card alert-card--warning">
                      <div>
                        <p className="alert-card__title">Correlation warning</p>
                        <p className="muted">{selectedOpportunity.correlationWarning}</p>
                      </div>
                    </article>
                  ) : null}

                  {blockedReason ? (
                    <article className="alert-card alert-card--critical">
                      <div>
                        <p className="alert-card__title">Execution blocked</p>
                        <p className="muted">{blockedReason}</p>
                      </div>
                    </article>
                  ) : null}

                  <label>
                    Stake override
                    <input
                      type="number"
                      min={0}
                      max={selectedOpportunity.maxStake}
                      step={100}
                      value={effectiveStakeOverride}
                      onChange={(event) => setStakeOverride(Number(event.target.value))}
                    />
                  </label>
                  <p className="muted">
                    Recommended {formatCurrency(selectedOpportunity.recommendedStake)} · current input{' '}
                    {formatCurrency(effectiveStakeOverride)} · max{' '}
                    {formatCurrency(selectedOpportunity.maxStake)} · entry range{' '}
                    {formatPercent(selectedOpportunity.entryPriceMin)} - {formatPercent(selectedOpportunity.entryPriceMax)}
                  </p>

                  <div className="action-row">
                    <button
                      className="button button--ghost"
                      type="button"
                      onClick={() => setModalAction('paper')}
                      disabled={Boolean(blockedReason)}
                    >
                      Send to paper
                    </button>
                    <button
                      className="button button--primary"
                      type="button"
                      onClick={() => setModalAction('live')}
                      disabled={Boolean(blockedReason)}
                    >
                      Approve live
                    </button>
                    <button className="button button--danger" type="button" onClick={() => setModalAction('reject')}>
                      Reject
                    </button>
                  </div>
                </Panel>

                <Panel title="Desk notes" subtitle={`Logged by ${sessionUser.name}`}>
                  <div className="note-stack">
                    {selectedOpportunity.notes.map((item) => (
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
                      placeholder="Capture why you approved, rejected, or routed this to paper."
                    />
                  </label>
                  <button className="button button--ghost" type="button" onClick={submitNote}>
                    Save note
                  </button>
                </Panel>

                <Panel title="Research attachments" subtitle="Links and uploaded files that support the decision">
                  <div className="attachment-stack">
                    {selectedOpportunity.attachments.map((attachment) => (
                      <article key={attachment.id} className="list-row">
                        <div className="list-row__main">
                          <p className="list-row__title">{attachment.title}</p>
                          <p className="muted">
                            {attachment.type === 'link' ? attachment.url : `${attachment.fileName} · ${attachment.sizeLabel}`}
                          </p>
                        </div>
                        <div className="list-row__meta">
                          <StatusPill tone="neutral">{attachment.type}</StatusPill>
                        </div>
                      </article>
                    ))}
                  </div>

                  <label>
                    Link title
                    <input value={linkTitle} onChange={(event) => setLinkTitle(event.target.value)} placeholder="Model note" />
                  </label>
                  <label>
                    Web link
                    <input value={linkUrl} onChange={(event) => setLinkUrl(event.target.value)} placeholder="https://..." />
                  </label>
                  <div className="action-row">
                    <button className="button button--ghost" type="button" onClick={submitLink}>
                      Add link
                    </button>
                    <label className="button button--ghost button--file">
                      Upload file
                      <input type="file" onChange={submitFile} />
                    </label>
                  </div>
                </Panel>
              </div>
            ) : (
              <Panel title="Opportunity detail" subtitle="Select a row from the table to inspect the strategy plan">
                <p className="muted">No opportunity matches the current filters.</p>
              </Panel>
            )}
          </aside>
        </section>
      </div>

      <ConfirmationModal
        open={modalAction !== null}
        title={
          modalAction === 'live'
            ? 'Approve this opportunity for live execution?'
            : modalAction === 'paper'
              ? 'Route this opportunity into paper trading?'
              : 'Reject this opportunity?'
        }
        description={
          modalAction === 'live'
            ? 'This is the final confirmation before the frontend would hand the execution request to the backend.'
            : modalAction === 'paper'
              ? 'This records the decision and stages the opportunity in the paper book for thesis validation.'
              : 'Rejected opportunities stay visible for traceability but move out of the action queue.'
        }
        confirmLabel={
          modalAction === 'live' ? 'Confirm live approval' : modalAction === 'paper' ? 'Route to paper' : 'Reject'
        }
        confirmTone={modalAction === 'reject' ? 'danger' : 'primary'}
        disabled={Boolean(blockedReason) && modalAction !== 'reject'}
        onCancel={() => setModalAction(null)}
        onConfirm={confirmAction}
      />
    </>
  )
}
