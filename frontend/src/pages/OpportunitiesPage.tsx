import { useDeferredValue, useEffect, useEffectEvent, useState } from 'react'

import { ConfirmationModal } from '../components/ConfirmationModal'
import { Panel } from '../components/Panel'
import { StatusPill } from '../components/StatusPill'
import { formatCompactCurrency, formatCurrency, formatPercent, formatRelativeTime } from '../lib/format'
import type { Opportunity, OpportunitySide, OrderbookSnapshot, SessionUser } from '../lib/types'

type RankMetric = 'volume24h' | 'liquidity' | 'tightness' | 'urgencyScore'

interface OpportunitiesPageProps {
  opportunities: Opportunity[]
  opportunityDetails: Record<string, Opportunity>
  orderbooks: Record<string, OrderbookSnapshot>
  sessionUser: SessionUser
  paperActionBlockedReason: string | null
  liveActionBlockedReason: string | null
  pausedCategories: string[]
  detailRefreshMs: number
  paperExecutionAvailable: boolean
  liveExecutionAvailable: boolean
  onApproveLive: (opportunityId: string, stakeOverride: number) => void
  onSendToPaper: (opportunityId: string, side: OpportunitySide, stakeOverride: number) => void
  onReject: (opportunityId: string) => void
  onAddNote: (opportunityId: string, text: string) => void
  onAddLink: (opportunityId: string, title: string, url: string) => void
  onAddFile: (opportunityId: string, file: File) => void
  onLoadDetail: (opportunityId: string) => Promise<Opportunity | null> | Opportunity | null | void
  onLoadOrderbook: (tokenId: string) => Promise<OrderbookSnapshot | null> | OrderbookSnapshot | null | void
}

function rankValue(opportunity: Opportunity, metric: RankMetric) {
  if (metric === 'tightness') {
    return opportunity.spreadBps ? 100000 - opportunity.spreadBps : 0
  }

  return opportunity[metric] ?? 0
}

export function OpportunitiesPage({
  opportunities,
  opportunityDetails,
  orderbooks,
  sessionUser,
  paperActionBlockedReason,
  liveActionBlockedReason,
  pausedCategories,
  detailRefreshMs,
  paperExecutionAvailable,
  liveExecutionAvailable,
  onApproveLive,
  onSendToPaper,
  onReject,
  onAddNote,
  onAddLink,
  onAddFile,
  onLoadDetail,
  onLoadOrderbook,
}: OpportunitiesPageProps) {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('All')
  const [status, setStatus] = useState('All')
  const [rankBy, setRankBy] = useState<RankMetric>('volume24h')
  const [selectedOpportunityId, setSelectedOpportunityId] = useState(opportunities[0]?.id ?? '')
  const [selectedSide, setSelectedSide] = useState<OpportunitySide>('YES')
  const [stakeOverride, setStakeOverride] = useState<number>(opportunities[0]?.defaultStake ?? 1000)
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
    .sort((left, right) => rankValue(right, rankBy) - rankValue(left, rankBy))

  const activeOpportunityId = selectedOpportunityId || filtered[0]?.id || ''
  const selectedSummary = filtered.find((opportunity) => opportunity.id === activeOpportunityId) ?? filtered[0] ?? null
  const selectedOpportunity = selectedSummary ? (opportunityDetails[selectedSummary.id] ?? selectedSummary) : null
  const defaultSide =
    (selectedOpportunity?.recommendedOutcome ??
      (selectedOpportunity?.tokenIds.YES ? 'YES' : selectedOpportunity?.tokenIds.NO ? 'NO' : 'YES')) as OpportunitySide
  const effectiveSide = selectedOpportunity?.tokenIds[selectedSide] ? selectedSide : defaultSide
  const effectiveStakeOverride =
    selectedOpportunity && activeOpportunityId !== selectedOpportunityId ? selectedOpportunity.defaultStake : stakeOverride

  const syncDetail = useEffectEvent(() => {
    if (!activeOpportunityId) {
      return
    }

    void onLoadDetail(activeOpportunityId)
  })

  useEffect(() => {
    if (!activeOpportunityId) {
      return
    }

    syncDetail()
    const timer = window.setInterval(() => {
      syncDetail()
    }, detailRefreshMs)

    return () => {
      window.clearInterval(timer)
    }
  }, [activeOpportunityId, detailRefreshMs])

  const selectedTokenId = selectedOpportunity?.tokenIds[effectiveSide] ?? selectedOpportunity?.defaultTokenId ?? null

  const syncOrderbook = useEffectEvent(() => {
    if (!selectedTokenId) {
      return
    }

    void onLoadOrderbook(selectedTokenId)
  })

  useEffect(() => {
    if (!selectedTokenId) {
      return
    }

    syncOrderbook()
    const timer = window.setInterval(() => {
      syncOrderbook()
    }, detailRefreshMs)

    return () => {
      window.clearInterval(timer)
    }
  }, [detailRefreshMs, selectedTokenId])

  const selectedOrderbook = selectedTokenId ? orderbooks[selectedTokenId] : null
  const categoryPaused = selectedOpportunity ? pausedCategories.includes(selectedOpportunity.category) : false
  const paperBlockedReason =
    paperActionBlockedReason ?? (categoryPaused ? `${selectedOpportunity?.category} is paused right now.` : null)

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

    if (modalAction === 'paper') {
      onSendToPaper(selectedOpportunity.id, effectiveSide, effectiveStakeOverride)
    }

    if (modalAction === 'live') {
      onApproveLive(selectedOpportunity.id, effectiveStakeOverride)
    }

    if (modalAction === 'reject') {
      onReject(selectedOpportunity.id)
    }

    setModalAction(null)
  }

  const outcomeRows = selectedOpportunity?.outcomes ?? []

  return (
    <>
      <div className="page-stack">
        <div className="hero-strip">
          <div>
            <p className="eyebrow">Opportunities</p>
            <h1>Review live Polymarket markets before any human-approved paper trade</h1>
            <p className="muted">
              The table now shows raw live markets, prices, liquidity, and orderbook detail. Strategy fields stay
              clearly unavailable until the backend research layer is wired in.
            </p>
          </div>
        </div>

        <section className="page-with-drawer">
          <div className="page-with-drawer__main">
            <Panel title="Candidate queue" subtitle="Categorized live markets from the backend">
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
                  ['volume24h', '24h volume'],
                  ['liquidity', 'Liquidity'],
                  ['tightness', 'Tight spread'],
                  ['urgencyScore', 'Soonest resolve'],
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
                      <th>Yes</th>
                      <th>No</th>
                      <th>Liquidity</th>
                      <th>Spread</th>
                      <th>Stage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((opportunity) => (
                      <tr
                        key={opportunity.id}
                        className={selectedOpportunity?.id === opportunity.id ? 'is-selected' : ''}
                        onClick={() => {
                          setSelectedOpportunityId(opportunity.id)
                          setSelectedSide(opportunity.tokenIds.YES ? 'YES' : 'NO')
                          setStakeOverride(opportunity.defaultStake)
                        }}
                      >
                        <td>{opportunity.question}</td>
                        <td>{opportunity.category}</td>
                        <td>{formatPercent(opportunity.yesPrice)}</td>
                        <td>{formatPercent(opportunity.noPrice)}</td>
                        <td>{formatCompactCurrency(opportunity.liquidity)}</td>
                        <td>{opportunity.spreadBps ? `${opportunity.spreadBps} bps` : 'N/A'}</td>
                        <td>{opportunity.statusLabel}</td>
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
                      <p className="metric-card__label">Yes / No</p>
                      <strong>
                        {formatPercent(selectedOpportunity.yesPrice)} / {formatPercent(selectedOpportunity.noPrice)}
                      </strong>
                      <span>Live market pricing</span>
                    </article>
                    <article className="metric-card">
                      <p className="metric-card__label">Liquidity</p>
                      <strong>{formatCompactCurrency(selectedOpportunity.liquidity)}</strong>
                      <span>{formatCompactCurrency(selectedOpportunity.marketDepth)} top-book depth</span>
                    </article>
                    <article className="metric-card">
                      <p className="metric-card__label">24h volume</p>
                      <strong>{formatCompactCurrency(selectedOpportunity.volume24h)}</strong>
                      <span>{selectedOpportunity.spreadBps ? `${selectedOpportunity.spreadBps} bps spread` : 'Spread unavailable'}</span>
                    </article>
                    <article className="metric-card">
                      <p className="metric-card__label">Resolution</p>
                      <strong>{selectedOpportunity.timeHorizon}</strong>
                      <span>
                        {selectedOpportunity.resolutionDate
                          ? `Ends ${formatRelativeTime(selectedOpportunity.resolutionDate)}`
                          : 'No resolution time returned'}
                      </span>
                    </article>
                  </div>

                  <div className="pill-row">
                    <StatusPill tone="info">{selectedOpportunity.category}</StatusPill>
                    <StatusPill tone="neutral">{selectedOpportunity.marketType}</StatusPill>
                    <StatusPill tone={selectedOpportunity.strategyAvailable ? 'positive' : 'warning'}>
                      {selectedOpportunity.strategyAvailable ? 'Strategy ready' : 'Strategy unavailable'}
                    </StatusPill>
                    {!paperExecutionAvailable ? <StatusPill tone="critical">Paper blocked</StatusPill> : null}
                    {!liveExecutionAvailable ? <StatusPill tone="warning">Live disabled</StatusPill> : null}
                  </div>

                  <div className="copy-block">
                    <p className="copy-block__label">Current backend readout</p>
                    <p>{selectedOpportunity.description || 'This is the raw live market metadata from Polymarket for desk review.'}</p>
                  </div>

                  <div className="copy-block">
                    <p className="copy-block__label">Strategy status</p>
                    <p>
                      Expected return, confidence, thesis, and invalidation stay unavailable in this milestone because
                      the strategy service is not connected yet.
                    </p>
                  </div>

                  <div className="table-shell">
                    <table>
                      <thead>
                        <tr>
                          <th>Outcome</th>
                          <th>Price</th>
                          <th>Best bid</th>
                          <th>Best ask</th>
                          <th>Depth</th>
                        </tr>
                      </thead>
                      <tbody>
                        {outcomeRows.map((outcome) => (
                          <tr key={`${selectedOpportunity.id}-${outcome.name}`}>
                            <td>{outcome.name}</td>
                            <td>{formatPercent(outcome.price)}</td>
                            <td>{formatPercent(outcome.bestBid)}</td>
                            <td>{formatPercent(outcome.bestAsk)}</td>
                            <td>{formatCompactCurrency(outcome.depth ?? 0)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <ul className="tag-list">
                    {selectedOpportunity.riskFlags.map((flag) => (
                      <li key={flag}>{flag}</li>
                    ))}
                  </ul>

                  {paperBlockedReason ? (
                    <article className="alert-card alert-card--critical">
                      <div>
                        <p className="alert-card__title">Paper execution blocked</p>
                        <p className="muted">{paperBlockedReason}</p>
                      </div>
                    </article>
                  ) : null}

                  {liveActionBlockedReason ? (
                    <article className="alert-card alert-card--warning">
                      <div>
                        <p className="alert-card__title">Live execution unavailable</p>
                        <p className="muted">{liveActionBlockedReason}</p>
                      </div>
                    </article>
                  ) : null}

                  <div className="segment-control">
                    {(['YES', 'NO'] as const).map((side) => (
                      <button
                        key={side}
                        className={`segment-control__button ${effectiveSide === side ? 'is-active' : ''}`}
                        type="button"
                        onClick={() => setSelectedSide(side)}
                        disabled={!selectedOpportunity.tokenIds[side]}
                      >
                        {side}
                      </button>
                    ))}
                  </div>

                  <label>
                    Paper ticket size
                    <input
                      type="number"
                      min={100}
                      max={selectedOpportunity.maxStake}
                      step={100}
                      value={effectiveStakeOverride}
                      onChange={(event) => setStakeOverride(Number(event.target.value))}
                    />
                  </label>
                  <p className="muted">
                    Default ticket {formatCurrency(selectedOpportunity.defaultStake)} · suggested ceiling{' '}
                    {formatCurrency(selectedOpportunity.maxStake)} · selected outcome {effectiveSide}
                  </p>

                  <div className="action-row">
                    <button
                      className="button button--ghost"
                      type="button"
                      onClick={() => setModalAction('paper')}
                      disabled={Boolean(paperBlockedReason) || !selectedOpportunity.tokenIds[effectiveSide]}
                    >
                      Send to paper
                    </button>
                    <button className="button button--primary" type="button" onClick={() => setModalAction('live')} disabled>
                      Approve live
                    </button>
                    <button className="button button--danger" type="button" onClick={() => setModalAction('reject')}>
                      Reject
                    </button>
                  </div>
                </Panel>

                <Panel title="Orderbook" subtitle={selectedTokenId ? `Token ${selectedTokenId.slice(0, 12)}...` : 'Select an outcome'}>
                  {selectedOrderbook ? (
                    <>
                      <div className="detail-grid">
                        <article className="metric-card">
                          <p className="metric-card__label">Best bid</p>
                          <strong>{formatPercent(selectedOrderbook.best_bid)}</strong>
                          <span>Current bid</span>
                        </article>
                        <article className="metric-card">
                          <p className="metric-card__label">Best ask</p>
                          <strong>{formatPercent(selectedOrderbook.best_ask)}</strong>
                          <span>Current ask</span>
                        </article>
                        <article className="metric-card">
                          <p className="metric-card__label">Midpoint</p>
                          <strong>{formatPercent(selectedOrderbook.midpoint)}</strong>
                          <span>Orderbook midpoint</span>
                        </article>
                        <article className="metric-card">
                          <p className="metric-card__label">Spread</p>
                          <strong>{formatPercent(selectedOrderbook.spread)}</strong>
                          <span>Top-of-book spread</span>
                        </article>
                      </div>

                      <div className="table-shell">
                        <table>
                          <thead>
                            <tr>
                              <th>Bid price</th>
                              <th>Bid size</th>
                              <th>Ask price</th>
                              <th>Ask size</th>
                            </tr>
                          </thead>
                          <tbody>
                            {Array.from({
                              length: Math.max(selectedOrderbook.bids.length, selectedOrderbook.asks.length, 8),
                            }).map((_, index) => {
                              const bid = selectedOrderbook.bids[index]
                              const ask = selectedOrderbook.asks[index]
                              return (
                                <tr key={`${selectedOrderbook.token_id}-${index}`}>
                                  <td>{formatPercent(bid?.price)}</td>
                                  <td>{bid ? bid.size.toFixed(0) : 'N/A'}</td>
                                  <td>{formatPercent(ask?.price)}</td>
                                  <td>{ask ? ask.size.toFixed(0) : 'N/A'}</td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      </div>
                    </>
                  ) : (
                    <p className="muted">Choose a token side to load the live orderbook.</p>
                  )}
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
                      placeholder="Capture why you papered, skipped, or rejected this live market."
                    />
                  </label>
                  <button className="button button--ghost" type="button" onClick={submitNote}>
                    Save note
                  </button>
                </Panel>

                <Panel title="Research attachments" subtitle="Links and uploaded files kept on the frontend prototype">
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
                    <input value={linkTitle} onChange={(event) => setLinkTitle(event.target.value)} placeholder="Research memo" />
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
              <Panel title="Opportunity detail" subtitle="Select a live market to inspect the backend detail">
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
            ? 'Approve this market for live execution?'
            : modalAction === 'paper'
              ? 'Submit this market to paper trading?'
              : 'Reject this market from the local review queue?'
        }
        description={
          modalAction === 'live'
            ? 'Live execution is intentionally disabled in this milestone, so this button remains a placeholder for Phase 2.'
            : modalAction === 'paper'
              ? `This sends a paper ${effectiveSide} trade to the backend and keeps the final human confirmation gate in the frontend.`
              : 'Rejected markets stay visible for traceability but move out of the active desk queue.'
        }
        confirmLabel={modalAction === 'live' ? 'Live unavailable' : modalAction === 'paper' ? 'Submit paper trade' : 'Reject'}
        confirmTone={modalAction === 'reject' ? 'danger' : 'primary'}
        disabled={modalAction === 'live' || (modalAction === 'paper' && Boolean(paperBlockedReason))}
        onCancel={() => setModalAction(null)}
        onConfirm={confirmAction}
      />
    </>
  )
}
