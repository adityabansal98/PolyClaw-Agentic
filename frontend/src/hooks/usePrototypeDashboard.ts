import { startTransition, useEffect, useEffectEvent, useState } from 'react'

import type {
  AlertItem,
  DecisionNote,
  LogEvent,
  Opportunity,
  OpportunitySide,
  OrderbookSnapshot,
  OverviewPayload,
  PortfolioSummary,
  Position,
  PositionsPayload,
  ResearchAttachment,
  SessionUser,
  TradePayload,
  UserAccount,
  UserRole,
} from '../lib/types'

const OPPORTUNITIES_REFRESH_MS = 8000
const OVERVIEW_REFRESH_MS = 12000
const POSITIONS_REFRESH_MS = 12000
const DETAIL_REFRESH_MS = 9000

const USERS_KEY = 'polyclaw.users'
const SESSION_KEY = 'polyclaw.session'
const OPPORTUNITY_OVERLAYS_KEY = 'polyclaw.opportunity-overlays'
const POSITION_OVERLAYS_KEY = 'polyclaw.position-overlays'
const PAUSED_CATEGORIES_KEY = 'polyclaw.paused-categories'
const KILL_SWITCH_KEY = 'polyclaw.kill-switch'

const seedUsers: UserAccount[] = [
  {
    id: 'user-alex',
    name: 'Alex Chen',
    email: 'alex@polyclaw.local',
    password: 'demo1234',
    role: 'trader',
    createdAt: '2026-04-11T14:00:00.000Z',
  },
  {
    id: 'user-maya',
    name: 'Maya Patel',
    email: 'maya@polyclaw.local',
    password: 'demo1234',
    role: 'analyst',
    createdAt: '2026-04-11T14:05:00.000Z',
  },
]

const emptySummary: PortfolioSummary = {
  environment: 'paper',
  available: false,
  totalReturnImmediate: null,
  openExposure: 0,
  availableCapital: null,
  activePositions: 0,
  pendingApprovals: 0,
  realizedPnl: null,
  unrealizedPnl: null,
  dailyPnl: null,
  liquidationValue: 0,
}

const emptyOverview: OverviewPayload = {
  generatedAt: new Date(0).toISOString(),
  lastRefreshAt: new Date(0).toISOString(),
  backendHealthSummary: {
    status: 'down',
    paperExecutionAvailable: false,
    liveExecutionAvailable: false,
    liveHoldingsAvailable: false,
  },
  dataFreshness: {
    opportunities: { name: 'opportunities', available: false, stale: true, updatedAt: null, ageSeconds: null, error: null },
    portfolio: { name: 'portfolio', available: false, stale: true, updatedAt: null, ageSeconds: null, error: null },
    positions: { name: 'positions', available: false, stale: true, updatedAt: null, ageSeconds: null, error: null },
  },
  paperSummary: emptySummary,
  liveSummary: {
    environment: 'live',
    available: false,
    totalReturnImmediate: null,
    openExposure: 0,
    availableCapital: null,
    activePositions: 0,
    pendingApprovals: 0,
    realizedPnl: null,
    unrealizedPnl: null,
    dailyPnl: null,
    liquidationValue: 0,
  },
  paperPositionsCount: 0,
  pendingOpportunityCount: 0,
  alerts: [],
  services: [],
}

type OpportunityOverlay = {
  currentStage?: Opportunity['currentStage']
  statusLabel?: string
  reviewer?: string
  reviewedAt?: string
  notes: DecisionNote[]
  attachments: ResearchAttachment[]
  snapshot?: Opportunity
}

type PositionOverlay = {
  notes: DecisionNote[]
  status?: Position['status']
}

function readStorage<T>(key: string, fallback: T): T {
  const raw = window.localStorage.getItem(key)
  if (!raw) {
    return fallback
  }

  try {
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

function persistStorage<T>(key: string, value: T) {
  window.localStorage.setItem(key, JSON.stringify(value))
}

function readUsers(): UserAccount[] {
  const raw = window.localStorage.getItem(USERS_KEY)
  if (!raw) {
    persistStorage(USERS_KEY, seedUsers)
    return seedUsers
  }

  try {
    return JSON.parse(raw) as UserAccount[]
  } catch {
    persistStorage(USERS_KEY, seedUsers)
    return seedUsers
  }
}

function readSession(): SessionUser | null {
  return readStorage<SessionUser | null>(SESSION_KEY, null)
}

function persistSession(user: SessionUser | null) {
  if (!user) {
    window.localStorage.removeItem(SESSION_KEY)
    return
  }

  persistStorage(SESSION_KEY, user)
}

function toSessionUser(account: UserAccount): SessionUser {
  return {
    id: account.id,
    name: account.name,
    email: account.email,
    role: account.role,
  }
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  const payload = (await response.json()) as Record<string, unknown>
  if (!response.ok) {
    const message = typeof payload.error === 'string' ? payload.error : `Request failed: ${response.status}`
    throw new Error(message)
  }

  return payload as T
}

function buildNote(author: string, text: string): DecisionNote {
  return {
    id: crypto.randomUUID(),
    author,
    createdAt: new Date().toISOString(),
    context: 'decision',
    text,
  }
}

function mergeOpportunity(opportunity: Opportunity, overlay?: OpportunityOverlay): Opportunity {
  return {
    ...opportunity,
    currentStage: overlay?.currentStage ?? opportunity.currentStage,
    statusLabel: overlay?.statusLabel ?? opportunity.statusLabel,
    reviewer: overlay?.reviewer ?? opportunity.reviewer,
    reviewedAt: overlay?.reviewedAt ?? opportunity.reviewedAt,
    notes: [...(overlay?.notes ?? []), ...(opportunity.notes ?? [])],
    attachments: [...(overlay?.attachments ?? []), ...(opportunity.attachments ?? [])],
  }
}

function mergePosition(position: Position, overlay?: PositionOverlay): Position {
  return {
    ...position,
    status: overlay?.status ?? position.status,
    notes: [...(overlay?.notes ?? []), ...(position.notes ?? [])],
  }
}

function uniqueById<T extends { id: string }>(items: T[]): T[] {
  const seen = new Set<string>()
  return items.filter((item) => {
    if (seen.has(item.id)) {
      return false
    }
    seen.add(item.id)
    return true
  })
}

function rankOpportunities(items: Opportunity[]): Opportunity[] {
  return [...items].sort((left, right) => {
    const leftStageWeight = left.currentStage === 'rejected' ? -1 : left.currentStage === 'paper' ? 1 : 2
    const rightStageWeight = right.currentStage === 'rejected' ? -1 : right.currentStage === 'paper' ? 1 : 2
    if (leftStageWeight !== rightStageWeight) {
      return rightStageWeight - leftStageWeight
    }

    return (right.volume24h ?? 0) - (left.volume24h ?? 0)
  })
}

function isStrategyUnavailable(opportunity: Opportunity) {
  return !opportunity.strategyAvailable
}

export function usePrototypeDashboard() {
  const [accounts, setAccounts] = useState<UserAccount[]>(() => readUsers())
  const [sessionUser, setSessionUser] = useState<SessionUser | null>(() => readSession())
  const [authError, setAuthError] = useState('')

  const [overview, setOverview] = useState<OverviewPayload>(emptyOverview)
  const [remoteOpportunities, setRemoteOpportunities] = useState<Opportunity[]>([])
  const [remotePositions, setRemotePositions] = useState<Position[]>([])
  const [opportunityDetails, setOpportunityDetails] = useState<Record<string, Opportunity>>({})
  const [orderbooks, setOrderbooks] = useState<Record<string, OrderbookSnapshot>>({})

  const [opportunityOverlays, setOpportunityOverlays] = useState<Record<string, OpportunityOverlay>>(() =>
    readStorage<Record<string, OpportunityOverlay>>(OPPORTUNITY_OVERLAYS_KEY, {}),
  )
  const [positionOverlays, setPositionOverlays] = useState<Record<string, PositionOverlay>>(() =>
    readStorage<Record<string, PositionOverlay>>(POSITION_OVERLAYS_KEY, {}),
  )
  const [pausedCategories, setPausedCategories] = useState<string[]>(() =>
    readStorage<string[]>(PAUSED_CATEGORIES_KEY, []),
  )
  const [killSwitchEnabled, setKillSwitchEnabled] = useState<boolean>(() => readStorage<boolean>(KILL_SWITCH_KEY, false))
  const [pendingKillSwitchAction, setPendingKillSwitchAction] = useState(false)
  const [logs, setLogs] = useState<LogEvent[]>([])

  useEffect(() => {
    persistStorage(OPPORTUNITY_OVERLAYS_KEY, opportunityOverlays)
  }, [opportunityOverlays])

  useEffect(() => {
    persistStorage(POSITION_OVERLAYS_KEY, positionOverlays)
  }, [positionOverlays])

  useEffect(() => {
    persistStorage(PAUSED_CATEGORIES_KEY, pausedCategories)
  }, [pausedCategories])

  useEffect(() => {
    persistStorage(KILL_SWITCH_KEY, killSwitchEnabled)
  }, [killSwitchEnabled])

  function appendLog(message: string, source: string, level: 'info' | 'warning' | 'error', user?: string) {
    setLogs((previous) => [
      {
        id: crypto.randomUUID(),
        timestamp: new Date().toISOString(),
        level,
        source,
        message,
        user,
      },
      ...previous,
    ].slice(0, 24))
  }

  async function refreshOverview() {
    try {
      const nextOverview = await requestJson<OverviewPayload>('/api/dashboard/overview')
      startTransition(() => {
        setOverview(nextOverview)
      })
    } catch (error) {
      appendLog(
        error instanceof Error ? error.message : 'Failed to refresh dashboard overview.',
        'overview-refresh',
        'error',
      )
    }
  }

  async function refreshOpportunities() {
    try {
      const payload = await requestJson<{ items: Opportunity[] }>('/api/opportunities')
      startTransition(() => {
        setRemoteOpportunities(payload.items)
      })
    } catch (error) {
      appendLog(
        error instanceof Error ? error.message : 'Failed to refresh opportunities.',
        'opportunity-refresh',
        'error',
      )
    }
  }

  async function refreshPositions() {
    try {
      const payload = await requestJson<PositionsPayload>('/api/positions?environment=paper')
      startTransition(() => {
        setRemotePositions(payload.items)
      })
    } catch (error) {
      appendLog(
        error instanceof Error ? error.message : 'Failed to refresh positions.',
        'positions-refresh',
        'error',
      )
    }
  }

  async function refreshAll() {
    await Promise.all([refreshOverview(), refreshOpportunities(), refreshPositions()])
  }

  const pollOverview = useEffectEvent(() => {
    void refreshOverview()
  })

  const pollOpportunities = useEffectEvent(() => {
    void refreshOpportunities()
  })

  const pollPositions = useEffectEvent(() => {
    void refreshPositions()
  })

  const pollAll = useEffectEvent(() => {
    void refreshAll()
  })

  useEffect(() => {
    if (!sessionUser) {
      return
    }

    pollAll()

    const overviewTimer = window.setInterval(() => {
      pollOverview()
    }, OVERVIEW_REFRESH_MS)
    const opportunitiesTimer = window.setInterval(() => {
      pollOpportunities()
    }, OPPORTUNITIES_REFRESH_MS)
    const positionsTimer = window.setInterval(() => {
      pollPositions()
    }, POSITIONS_REFRESH_MS)

    return () => {
      window.clearInterval(overviewTimer)
      window.clearInterval(opportunitiesTimer)
      window.clearInterval(positionsTimer)
    }
  }, [sessionUser])

  function signIn(email: string, password: string) {
    const account = accounts.find((candidate) => candidate.email === email && candidate.password === password)
    if (!account) {
      setAuthError('Email or password did not match a known account.')
      return
    }

    const session = toSessionUser(account)
    persistSession(session)
    setSessionUser(session)
    setAuthError('')
  }

  function createAccount(payload: { name: string; email: string; password: string; role: UserRole }) {
    if (!payload.name.trim() || !payload.email.trim() || !payload.password.trim()) {
      setAuthError('Name, email, and password are all required.')
      return
    }

    if (accounts.some((account) => account.email === payload.email.trim())) {
      setAuthError('That email already exists in the prototype account store.')
      return
    }

    const account: UserAccount = {
      id: crypto.randomUUID(),
      name: payload.name.trim(),
      email: payload.email.trim(),
      password: payload.password,
      role: payload.role,
      createdAt: new Date().toISOString(),
    }

    const nextAccounts = [...accounts, account]
    setAccounts(nextAccounts)
    persistStorage(USERS_KEY, nextAccounts)

    const session = toSessionUser(account)
    setSessionUser(session)
    persistSession(session)
    setAuthError('')
  }

  function signOut() {
    setSessionUser(null)
    persistSession(null)
  }

  const mergedRemoteOpportunities = remoteOpportunities.map((opportunity) =>
    mergeOpportunity(opportunity, opportunityOverlays[opportunity.id]),
  )
  const overlayOnlyOpportunities = Object.values(opportunityOverlays)
    .map((overlay) => overlay.snapshot)
    .filter((snapshot): snapshot is Opportunity => Boolean(snapshot))
    .filter((snapshot) => !remoteOpportunities.some((opportunity) => opportunity.id === snapshot.id))
    .map((opportunity) => mergeOpportunity(opportunity, opportunityOverlays[opportunity.id]))

  const opportunities = rankOpportunities(uniqueById([...mergedRemoteOpportunities, ...overlayOnlyOpportunities]))
  const positions = remotePositions.map((position) => mergePosition(position, positionOverlays[position.id]))

  const paperSummary = overview.paperSummary
  const liveSummary = overview.liveSummary
  const lastRefreshAt = overview.lastRefreshAt

  const alerts: AlertItem[] = [...overview.alerts]
  if (killSwitchEnabled) {
    alerts.unshift({
      id: 'local-kill-switch',
      tone: 'critical',
      title: 'Kill switch is enabled',
      description: 'Paper trade submissions are blocked locally until the desk disables the switch.',
    })
  }
  if (pausedCategories.length > 0) {
    alerts.push({
      id: 'local-paused-categories',
      tone: 'warning',
      title: 'Category pauses are active',
      description: `New paper trades are paused for ${pausedCategories.join(', ')} while the team reviews risk.`,
    })
  }

  const paperActionBlockedReason = killSwitchEnabled
    ? 'Global kill switch is enabled.'
    : !overview.backendHealthSummary.paperExecutionAvailable
      ? 'Paper execution is currently unavailable.'
      : overview.dataFreshness.opportunities.stale
        ? 'Opportunity data is stale. Wait for the backend to refresh before trading.'
        : overview.dataFreshness.portfolio.stale
          ? 'Paper portfolio data is stale. Wait for the backend to refresh before trading.'
          : null

  const liveActionBlockedReason = killSwitchEnabled
    ? 'Global kill switch is enabled.'
    : !overview.backendHealthSummary.liveExecutionAvailable
      ? 'Live execution is disabled in Phase 1. Paper first, then promote similar logic later.'
      : null

  function updateOpportunityOverlay(opportunityId: string, updater: (current: OpportunityOverlay) => OpportunityOverlay) {
    setOpportunityOverlays((previous) => {
      const current = previous[opportunityId] ?? { notes: [], attachments: [] }
      return {
        ...previous,
        [opportunityId]: updater(current),
      }
    })
  }

  function updatePositionOverlay(positionId: string, updater: (current: PositionOverlay) => PositionOverlay) {
    setPositionOverlays((previous) => {
      const current = previous[positionId] ?? { notes: [] }
      return {
        ...previous,
        [positionId]: updater(current),
      }
    })
  }

  function addOpportunityNote(opportunityId: string, text: string) {
    if (!sessionUser) {
      return
    }

    updateOpportunityOverlay(opportunityId, (current) => ({
      ...current,
      notes: [buildNote(sessionUser.name, text), ...current.notes],
    }))
    appendLog(`Added a note to ${opportunityId}.`, 'opportunity-notes', 'info', sessionUser.name)
  }

  function addPositionNote(positionId: string, text: string) {
    if (!sessionUser) {
      return
    }

    updatePositionOverlay(positionId, (current) => ({
      ...current,
      notes: [buildNote(sessionUser.name, text), ...current.notes],
    }))
    appendLog(`Added a note to paper position ${positionId}.`, 'position-notes', 'info', sessionUser.name)
  }

  function addOpportunityLink(opportunityId: string, title: string, url: string) {
    if (!sessionUser) {
      return
    }

    const attachment: ResearchAttachment = {
      id: crypto.randomUUID(),
      type: 'link',
      title,
      url,
      uploadedBy: sessionUser.name,
      uploadedAt: new Date().toISOString(),
    }

    updateOpportunityOverlay(opportunityId, (current) => ({
      ...current,
      attachments: [attachment, ...current.attachments],
    }))
    appendLog(`Attached a research link to ${opportunityId}.`, 'research-links', 'info', sessionUser.name)
  }

  function addOpportunityFile(opportunityId: string, file: File) {
    if (!sessionUser) {
      return
    }

    const sizeLabel = file.size > 1000000 ? `${(file.size / 1000000).toFixed(1)} MB` : `${Math.round(file.size / 1000)} KB`
    const attachment: ResearchAttachment = {
      id: crypto.randomUUID(),
      type: 'file',
      title: file.name,
      fileName: file.name,
      sizeLabel,
      uploadedBy: sessionUser.name,
      uploadedAt: new Date().toISOString(),
    }

    updateOpportunityOverlay(opportunityId, (current) => ({
      ...current,
      attachments: [attachment, ...current.attachments],
    }))
    appendLog(`Attached a local research file to ${opportunityId}.`, 'research-files', 'info', sessionUser.name)
  }

  function rejectOpportunity(opportunityId: string) {
    if (!sessionUser) {
      return
    }

    const snapshot = opportunities.find((opportunity) => opportunity.id === opportunityId)
    updateOpportunityOverlay(opportunityId, (current) => ({
      ...current,
      currentStage: 'rejected',
      statusLabel: 'Rejected locally',
      reviewer: sessionUser.name,
      reviewedAt: new Date().toISOString(),
      snapshot: snapshot ?? current.snapshot,
    }))
    appendLog(`Rejected opportunity ${opportunityId}.`, 'approval-flow', 'warning', sessionUser.name)
  }

  async function loadOpportunityDetail(opportunityId: string) {
    try {
      const detail = await requestJson<Opportunity>(`/api/opportunities/${opportunityId}`)
      const merged = mergeOpportunity(detail, opportunityOverlays[opportunityId])
      startTransition(() => {
        setOpportunityDetails((previous) => ({ ...previous, [opportunityId]: merged }))
      })
      return merged
    } catch (error) {
      appendLog(
        error instanceof Error ? error.message : `Failed to load detail for ${opportunityId}.`,
        'opportunity-detail',
        'error',
      )
      return null
    }
  }

  async function loadOrderbook(tokenId: string) {
    try {
      const orderbook = await requestJson<OrderbookSnapshot>(`/api/orderbook/${tokenId}`)
      startTransition(() => {
        setOrderbooks((previous) => ({ ...previous, [tokenId]: orderbook }))
      })
      return orderbook
    } catch (error) {
      appendLog(
        error instanceof Error ? error.message : `Failed to load orderbook for ${tokenId}.`,
        'orderbook-detail',
        'error',
      )
      return null
    }
  }

  async function submitTrade(payload: TradePayload) {
    const response = await requestJson<{
      status: string
      message: string
      filled_price?: number
      filled_size?: number
      total_cost?: number
    }>('/api/trade', {
      method: 'POST',
      body: JSON.stringify(payload),
    })

    await Promise.all([refreshOverview(), refreshPositions(), refreshOpportunities()])
    return response
  }

  async function sendToPaper(opportunityId: string, side: OpportunitySide, stakeOverride: number) {
    if (!sessionUser) {
      return
    }

    const opportunity = opportunities.find((candidate) => candidate.id === opportunityId)
    if (!opportunity) {
      appendLog(`Could not find ${opportunityId} in the current opportunity feed.`, 'paper-trading', 'error', sessionUser.name)
      return
    }

    if (paperActionBlockedReason) {
      appendLog(`Paper trade blocked for ${opportunityId}: ${paperActionBlockedReason}`, 'paper-trading', 'warning', sessionUser.name)
      return
    }

    if (pausedCategories.includes(opportunity.category)) {
      appendLog(`Paper trade blocked for paused category ${opportunity.category}.`, 'paper-trading', 'warning', sessionUser.name)
      return
    }

    const tokenId = opportunity.tokenIds[side]
    const outcome = opportunity.outcomes.find((candidate) => candidate.name.toUpperCase() === side)?.name ?? side
    if (!tokenId) {
      appendLog(`No ${side} token is available for ${opportunity.question}.`, 'paper-trading', 'error', sessionUser.name)
      return
    }

    try {
      const result = await submitTrade({
        environment: 'paper',
        token_id: tokenId,
        market_id: opportunity.id,
        opportunityId,
        question: opportunity.question,
        outcome,
        side: 'BUY',
        size: stakeOverride,
      })

      updateOpportunityOverlay(opportunityId, (current) => ({
        ...current,
        currentStage: 'paper',
        statusLabel: result.status === 'FILLED' ? 'Paper order filled' : 'Paper order submitted',
        reviewer: sessionUser.name,
        reviewedAt: new Date().toISOString(),
        snapshot: opportunity,
      }))

      appendLog(
        `Submitted paper ${side} trade for ${opportunity.question} at ${Math.round(stakeOverride)} USD notional.`,
        'paper-trading',
        'info',
        sessionUser.name,
      )
    } catch (error) {
      appendLog(
        error instanceof Error ? error.message : `Paper trade failed for ${opportunityId}.`,
        'paper-trading',
        'error',
        sessionUser.name,
      )
    }
  }

  async function approveOpportunity(opportunityId: string, stakeOverride: number) {
    if (!sessionUser) {
      return
    }

    appendLog(
      `Live execution remains disabled in Phase 1. ${opportunityId} stayed in review only at ${Math.round(stakeOverride)} USD.`,
      'live-approval',
      'warning',
      sessionUser.name,
    )
  }

  async function closePosition(positionId: string) {
    if (!sessionUser) {
      return
    }

    const position = positions.find((candidate) => candidate.id === positionId)
    if (!position) {
      return
    }

    if (paperActionBlockedReason) {
      appendLog(`Close blocked for ${position.question}: ${paperActionBlockedReason}`, 'position-management', 'warning', sessionUser.name)
      return
    }

    try {
      await submitTrade({
        environment: 'paper',
        token_id: position.tokenId,
        market_id: position.marketId,
        question: position.question,
        outcome: position.outcome,
        side: 'SELL',
        size: position.shares,
      })
      appendLog(`Closed paper position ${position.question}.`, 'position-management', 'warning', sessionUser.name)
    } catch (error) {
      appendLog(
        error instanceof Error ? error.message : `Failed to close ${position.question}.`,
        'position-management',
        'error',
        sessionUser.name,
      )
    }
  }

  async function resizePosition(positionId: string, direction: 'increase' | 'reduce', amount: number) {
    if (!sessionUser) {
      return
    }

    const position = positions.find((candidate) => candidate.id === positionId)
    if (!position) {
      return
    }

    if (paperActionBlockedReason) {
      appendLog(`Resize blocked for ${position.question}: ${paperActionBlockedReason}`, 'position-management', 'warning', sessionUser.name)
      return
    }

    try {
      if (direction === 'increase') {
        await submitTrade({
          environment: 'paper',
          token_id: position.tokenId,
          market_id: position.marketId,
          question: position.question,
          outcome: position.outcome,
          side: 'BUY',
          size: amount,
        })
      } else {
        const sharesToSell = position.currentPrice > 0 ? amount / position.currentPrice : 0
        await submitTrade({
          environment: 'paper',
          token_id: position.tokenId,
          market_id: position.marketId,
          question: position.question,
          outcome: position.outcome,
          side: 'SELL',
          size: sharesToSell,
        })
      }

      appendLog(
        `${direction === 'increase' ? 'Increased' : 'Reduced'} paper position ${position.question} by ${Math.round(amount)} USD.`,
        'position-management',
        'info',
        sessionUser.name,
      )
    } catch (error) {
      appendLog(
        error instanceof Error ? error.message : `Failed to update ${position.question}.`,
        'position-management',
        'error',
        sessionUser.name,
      )
    }
  }

  function markPositionReview(positionId: string) {
    if (!sessionUser) {
      return
    }

    updatePositionOverlay(positionId, (current) => ({
      ...current,
      status: 'review',
    }))
    appendLog(`Marked paper position ${positionId} for review.`, 'risk-controls', 'warning', sessionUser.name)
  }

  function pauseCategory(category: string) {
    if (!sessionUser || pausedCategories.includes(category)) {
      return
    }

    setPausedCategories((previous) => [...previous, category])
    appendLog(`Paused new paper trades for ${category}.`, 'risk-controls', 'warning', sessionUser.name)
  }

  function confirmToggleKillSwitch() {
    setPendingKillSwitchAction((current) => !current)
  }

  function executeToggleKillSwitch() {
    setKillSwitchEnabled((current) => !current)
    setPendingKillSwitchAction(false)
    appendLog(
      `Kill switch ${killSwitchEnabled ? 'disabled' : 'enabled'}.`,
      'operations',
      killSwitchEnabled ? 'warning' : 'error',
      sessionUser?.name,
    )
  }

  const paperOpportunities = opportunities.filter((opportunity) => opportunity.currentStage === 'paper')
  const topOpportunities = opportunities.filter((opportunity) => opportunity.currentStage !== 'rejected')
  const strategyUnavailableCount = opportunities.filter((opportunity) => isStrategyUnavailable(opportunity)).length

  return {
    sessionUser,
    authError,
    signIn,
    createAccount,
    signOut,
    refreshAll,
    liveSummary,
    paperSummary,
    opportunities,
    topOpportunities,
    paperOpportunities,
    positions,
    services: overview.services,
    logs,
    pausedCategories,
    alerts,
    lastRefreshAt,
    paperActionBlockedReason,
    liveActionBlockedReason,
    killSwitchEnabled,
    pendingKillSwitchAction,
    confirmToggleKillSwitch,
    cancelToggleKillSwitch: () => setPendingKillSwitchAction(false),
    executeToggleKillSwitch,
    addOpportunityNote,
    addPositionNote,
    addOpportunityLink,
    addOpportunityFile,
    approveOpportunity,
    sendToPaper,
    rejectOpportunity,
    promotePaperOpportunity: approveOpportunity,
    closePosition,
    resizePosition,
    markPositionReview,
    pauseCategory,
    loadOpportunityDetail,
    opportunityDetails,
    loadOrderbook,
    orderbooks,
    detailRefreshMs: DETAIL_REFRESH_MS,
    paperExecutionAvailable: overview.backendHealthSummary.paperExecutionAvailable,
    liveExecutionAvailable: overview.backendHealthSummary.liveExecutionAvailable,
    liveHoldingsAvailable: overview.backendHealthSummary.liveHoldingsAvailable,
    freshness: overview.dataFreshness,
    strategyUnavailableCount,
  }
}
