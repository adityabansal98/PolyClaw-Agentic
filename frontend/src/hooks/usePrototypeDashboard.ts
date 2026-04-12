import { startTransition, useEffect, useEffectEvent, useState } from 'react'

import { initialDashboardState, seedUsers } from '../lib/mockData'
import type {
  AlertItem,
  DashboardState,
  Environment,
  Opportunity,
  PortfolioSummary,
  Position,
  SessionUser,
  UserAccount,
  UserRole,
} from '../lib/types'

const LIVE_STARTING_CAPITAL = 156000
const PAPER_STARTING_CAPITAL = 100000
const AUTO_REFRESH_MS = 12000
const USERS_KEY = 'polyclaw.users'
const SESSION_KEY = 'polyclaw.session'

function readUsers(): UserAccount[] {
  const raw = window.localStorage.getItem(USERS_KEY)
  if (!raw) {
    window.localStorage.setItem(USERS_KEY, JSON.stringify(seedUsers))
    return seedUsers
  }

  return JSON.parse(raw) as UserAccount[]
}

function readSession(): SessionUser | null {
  const raw = window.localStorage.getItem(SESSION_KEY)
  return raw ? (JSON.parse(raw) as SessionUser) : null
}

function persistUsers(users: UserAccount[]) {
  window.localStorage.setItem(USERS_KEY, JSON.stringify(users))
}

function persistSession(user: SessionUser | null) {
  if (!user) {
    window.localStorage.removeItem(SESSION_KEY)
    return
  }

  window.localStorage.setItem(SESSION_KEY, JSON.stringify(user))
}

function priceDrift(seed: number, step: number, magnitude: number) {
  return ((((step + seed) % 7) - 3) / 3) * magnitude
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(Math.max(value, minimum), maximum)
}

function recalculatePosition(position: Position, price: number, updatedAt: string): Position {
  const liquidationValue = position.shares * price
  const unrealizedPnl = liquidationValue - position.stake

  return {
    ...position,
    currentPrice: price,
    liquidationValue,
    unrealizedPnl,
    updatedAt,
    priceHistory: [...position.priceHistory.slice(-5), price],
  }
}

function createPositionFromOpportunity(
  opportunity: Opportunity,
  environment: Environment,
): Position {
  const shares = opportunity.recommendedStake / opportunity.marketProbability
  const liquidationValue = shares * opportunity.marketProbability

  return {
    id: `${environment}-${opportunity.id}-${crypto.randomUUID().slice(0, 8)}`,
    opportunityId: opportunity.id,
    environment,
    question: opportunity.question,
    category: opportunity.category,
    marketType: opportunity.marketType,
    side: opportunity.side,
    shares,
    stake: opportunity.recommendedStake,
    entryPrice: opportunity.marketProbability,
    currentPrice: opportunity.marketProbability,
    liquidationValue,
    unrealizedPnl: liquidationValue - opportunity.recommendedStake,
    status: 'open',
    openedAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    modelView: `Model probability ${Math.round(opportunity.modelProbability * 100)}% vs market ${Math.round(
      opportunity.marketProbability * 100,
    )}%.`,
    thesisAtEntry: opportunity.thesis,
    exitGuidance: opportunity.invalidation,
    relatedStrategy: opportunity.strategySummary,
    notes: [],
    tags: [...opportunity.tags, environment],
    priceHistory: opportunity.priceHistory.slice(-5),
  }
}

function buildSummary(
  environment: Environment,
  positions: Position[],
  cashBalance: number,
  realizedPnl: number,
  pendingApprovals: number,
): PortfolioSummary {
  const liquidationValue = positions.reduce((sum, position) => sum + position.liquidationValue, 0)
  const openExposure = positions.reduce((sum, position) => sum + position.stake, 0)
  const unrealizedPnl = positions.reduce((sum, position) => sum + position.unrealizedPnl, 0)
  const dailyPnl = positions.reduce((sum, position) => {
    const current = position.priceHistory[position.priceHistory.length - 1] ?? position.currentPrice
    const previous = position.priceHistory[position.priceHistory.length - 2] ?? position.entryPrice
    return sum + position.shares * (current - previous)
  }, 0)
  const startingCapital = environment === 'live' ? LIVE_STARTING_CAPITAL : PAPER_STARTING_CAPITAL
  const totalReturnImmediate = cashBalance + liquidationValue - startingCapital

  return {
    environment,
    totalReturnImmediate,
    openExposure,
    availableCapital: cashBalance,
    activePositions: positions.filter((position) => position.status !== 'closed').length,
    pendingApprovals,
    realizedPnl,
    unrealizedPnl,
    dailyPnl,
    liquidationValue,
  }
}

function buildAlerts(state: DashboardState): AlertItem[] {
  const alerts: AlertItem[] = []
  const criticalFailures = state.services.filter((service) => service.critical && service.status !== 'healthy')
  const paperQueue = state.opportunities.filter((opportunity) => opportunity.currentStage === 'paper').length
  const liveQueue = state.opportunities.filter((opportunity) => opportunity.currentStage === 'new').length

  if (state.killSwitchEnabled) {
    alerts.push({
      id: 'alert-kill-switch',
      tone: 'critical',
      title: 'Kill switch is enabled',
      description: 'New live approvals and promotions are blocked until the switch is disabled.',
    })
  }

  if (criticalFailures.length > 0) {
    alerts.push({
      id: 'alert-critical-services',
      tone: 'critical',
      title: 'Critical service health requires attention',
      description: `${criticalFailures.map((service) => service.name).join(', ')} must be healthy before execution.`,
    })
  }

  if (state.pausedCategories.length > 0) {
    alerts.push({
      id: 'alert-paused-categories',
      tone: 'warning',
      title: 'Category pauses are active',
      description: `Approvals are paused for ${state.pausedCategories.join(', ')} while the desk reviews risk.`,
    })
  }

  alerts.push({
    id: 'alert-opportunity-queue',
    tone: 'neutral',
    title: `${liveQueue} new opportunities are waiting for review`,
    description: `${paperQueue} opportunities remain in paper-first validation.`,
  })

  return alerts
}

function toSessionUser(account: UserAccount): SessionUser {
  return {
    id: account.id,
    name: account.name,
    email: account.email,
    role: account.role,
  }
}

export function usePrototypeDashboard() {
  const [accounts, setAccounts] = useState<UserAccount[]>(() => readUsers())
  const [sessionUser, setSessionUser] = useState<SessionUser | null>(() => readSession())
  const [authError, setAuthError] = useState('')
  const [pendingKillSwitchAction, setPendingKillSwitchAction] = useState(false)
  const [state, setState] = useState<DashboardState>(initialDashboardState)

  const refreshSnapshot = useEffectEvent(() => {
    startTransition(() => {
      setState((previous) => {
        const nextRefreshCount = previous.refreshCount + 1
        const now = new Date().toISOString()

        const opportunities = previous.opportunities.map((opportunity, index) => {
          const marketProbability = clamp(
            opportunity.marketProbability + priceDrift(index + opportunity.question.length, nextRefreshCount, 0.004),
            0.05,
            0.95,
          )
          const edge = opportunity.modelProbability - marketProbability
          const expectedReturn = edge * 0.9

          return {
            ...opportunity,
            marketProbability,
            edge,
            expectedReturn,
            lastUpdatedAt: now,
            priceHistory: [...opportunity.priceHistory.slice(-5), marketProbability],
          }
        })

        const livePositions = previous.livePositions.map((position, index) => {
          const nextPrice = clamp(
            position.currentPrice + priceDrift(index + position.question.length, nextRefreshCount, 0.006),
            0.05,
            0.95,
          )
          return recalculatePosition(position, nextPrice, now)
        })

        const paperPositions = previous.paperPositions.map((position, index) => {
          const nextPrice = clamp(
            position.currentPrice + priceDrift(index + position.category.length, nextRefreshCount, 0.004),
            0.05,
            0.95,
          )
          return recalculatePosition(position, nextPrice, now)
        })

        const services = previous.services.map((service, index) => ({
          ...service,
          latencyMs: Math.round(clamp(service.latencyMs + priceDrift(index, nextRefreshCount, 60), 120, 1800)),
          lastHeartbeatAt: service.status === 'down' ? service.lastHeartbeatAt : now,
        }))

        return {
          ...previous,
          opportunities,
          livePositions,
          paperPositions,
          services,
          lastRefreshAt: now,
          refreshCount: nextRefreshCount,
        }
      })
    })
  })

  useEffect(() => {
    const timer = window.setInterval(() => {
      refreshSnapshot()
    }, AUTO_REFRESH_MS)

    return () => {
      window.clearInterval(timer)
    }
  }, [])

  function appendLog(message: string, source: string, level: 'info' | 'warning' | 'error', user?: string) {
    setState((previous) => ({
      ...previous,
      logs: [
        {
          id: crypto.randomUUID(),
          timestamp: new Date().toISOString(),
          level,
          source,
          message,
          user,
        },
        ...previous.logs,
      ].slice(0, 16),
    }))
  }

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

    if (accounts.some((account) => account.email === payload.email)) {
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
    persistUsers(nextAccounts)

    const session = toSessionUser(account)
    setSessionUser(session)
    persistSession(session)
    setAuthError('')
  }

  function signOut() {
    setSessionUser(null)
    persistSession(null)
  }

  function addOpportunityNote(opportunityId: string, text: string) {
    if (!sessionUser) {
      return
    }

    setState((previous) => ({
      ...previous,
      opportunities: previous.opportunities.map((opportunity) =>
        opportunity.id === opportunityId
          ? {
              ...opportunity,
              notes: [
                {
                  id: crypto.randomUUID(),
                  author: sessionUser.name,
                  createdAt: new Date().toISOString(),
                  context: 'decision',
                  text,
                },
                ...opportunity.notes,
              ],
            }
          : opportunity,
      ),
    }))

    appendLog(`Added a decision note to ${opportunityId}.`, 'opportunity-notes', 'info', sessionUser.name)
  }

  function addPositionNote(positionId: string, text: string) {
    if (!sessionUser) {
      return
    }

    setState((previous) => ({
      ...previous,
      livePositions: previous.livePositions.map((position) =>
        position.id === positionId
          ? {
              ...position,
              notes: [
                {
                  id: crypto.randomUUID(),
                  author: sessionUser.name,
                  createdAt: new Date().toISOString(),
                  context: 'decision',
                  text,
                },
                ...position.notes,
              ],
            }
          : position,
      ),
    }))

    appendLog(`Added a note to live position ${positionId}.`, 'position-notes', 'info', sessionUser.name)
  }

  function addOpportunityLink(opportunityId: string, title: string, url: string) {
    if (!sessionUser) {
      return
    }

    setState((previous) => ({
      ...previous,
      opportunities: previous.opportunities.map((opportunity) =>
        opportunity.id === opportunityId
          ? {
              ...opportunity,
              attachments: [
                {
                  id: crypto.randomUUID(),
                  type: 'link',
                  title,
                  url,
                  uploadedBy: sessionUser.name,
                  uploadedAt: new Date().toISOString(),
                },
                ...opportunity.attachments,
              ],
            }
          : opportunity,
      ),
    }))

    appendLog(`Attached a research link to ${opportunityId}.`, 'research-links', 'info', sessionUser.name)
  }

  function addOpportunityFile(opportunityId: string, file: File) {
    if (!sessionUser) {
      return
    }

    const sizeLabel = file.size > 1000000 ? `${(file.size / 1000000).toFixed(1)} MB` : `${Math.round(file.size / 1000)} KB`

    setState((previous) => ({
      ...previous,
      opportunities: previous.opportunities.map((opportunity) =>
        opportunity.id === opportunityId
          ? {
              ...opportunity,
              attachments: [
                {
                  id: crypto.randomUUID(),
                  type: 'file',
                  title: file.name,
                  fileName: file.name,
                  sizeLabel,
                  uploadedBy: sessionUser.name,
                  uploadedAt: new Date().toISOString(),
                },
                ...opportunity.attachments,
              ],
            }
          : opportunity,
      ),
    }))

    appendLog(`Uploaded a research file for ${opportunityId}.`, 'research-files', 'info', sessionUser.name)
  }

  function approveOpportunity(opportunityId: string, stakeOverride: number, target: 'live' | 'paper') {
    if (!sessionUser) {
      return
    }

    setState((previous) => {
      const opportunity = previous.opportunities.find((candidate) => candidate.id === opportunityId)
      if (!opportunity) {
        return previous
      }

      const updatedOpportunity: Opportunity = {
        ...opportunity,
        recommendedStake: stakeOverride,
        currentStage: target === 'live' ? 'approved' : 'paper',
        statusLabel: target === 'live' ? 'Approved for live execution' : 'Sent to paper',
        reviewer: sessionUser.name,
        reviewedAt: new Date().toISOString(),
      }

      const nextPosition = createPositionFromOpportunity(updatedOpportunity, target)

      return {
        ...previous,
        opportunities: previous.opportunities.map((candidate) => (candidate.id === opportunityId ? updatedOpportunity : candidate)),
        livePositions: target === 'live' ? [nextPosition, ...previous.livePositions] : previous.livePositions,
        paperPositions: target === 'paper' ? [nextPosition, ...previous.paperPositions] : previous.paperPositions,
        liveCashBalance: target === 'live' ? previous.liveCashBalance - stakeOverride : previous.liveCashBalance,
        paperCashBalance: target === 'paper' ? previous.paperCashBalance - stakeOverride : previous.paperCashBalance,
      }
    })

    appendLog(
      target === 'live'
        ? `Approved ${opportunityId} for live execution at ${Math.round(stakeOverride)} USD notional.`
        : `Routed ${opportunityId} into paper trading at ${Math.round(stakeOverride)} USD notional.`,
      target === 'live' ? 'approval-flow' : 'paper-routing',
      'info',
      sessionUser.name,
    )
  }

  function rejectOpportunity(opportunityId: string) {
    if (!sessionUser) {
      return
    }

    setState((previous) => ({
      ...previous,
      opportunities: previous.opportunities.map((opportunity) =>
        opportunity.id === opportunityId
          ? {
              ...opportunity,
              currentStage: 'rejected',
              statusLabel: 'Rejected',
              reviewer: sessionUser.name,
              reviewedAt: new Date().toISOString(),
            }
          : opportunity,
      ),
    }))

    appendLog(`Rejected opportunity ${opportunityId}.`, 'approval-flow', 'warning', sessionUser.name)
  }

  function promotePaperOpportunity(opportunityId: string, stakeOverride: number) {
    if (!sessionUser) {
      return
    }

    setState((previous) => {
      const opportunity = previous.opportunities.find((candidate) => candidate.id === opportunityId)
      if (!opportunity) {
        return previous
      }

      const updatedOpportunity: Opportunity = {
        ...opportunity,
        recommendedStake: stakeOverride,
        currentStage: 'approved',
        statusLabel: 'Promoted from paper to live',
        reviewer: sessionUser.name,
        reviewedAt: new Date().toISOString(),
      }

      const nextPosition = createPositionFromOpportunity(updatedOpportunity, 'live')

      return {
        ...previous,
        opportunities: previous.opportunities.map((candidate) => (candidate.id === opportunityId ? updatedOpportunity : candidate)),
        livePositions: [nextPosition, ...previous.livePositions],
        liveCashBalance: previous.liveCashBalance - stakeOverride,
      }
    })

    appendLog(`Promoted ${opportunityId} from paper to live.`, 'paper-promotion', 'info', sessionUser.name)
  }

  function closePosition(positionId: string) {
    if (!sessionUser) {
      return
    }

    setState((previous) => {
      const position = previous.livePositions.find((candidate) => candidate.id === positionId)
      if (!position) {
        return previous
      }

      return {
        ...previous,
        livePositions: previous.livePositions.filter((candidate) => candidate.id !== positionId),
        liveCashBalance: previous.liveCashBalance + position.liquidationValue,
        liveRealizedPnl: previous.liveRealizedPnl + position.unrealizedPnl,
      }
    })

    appendLog(`Closed live position ${positionId}.`, 'position-management', 'warning', sessionUser.name)
  }

  function resizePosition(positionId: string, direction: 'increase' | 'reduce', amount: number) {
    if (!sessionUser) {
      return
    }

    setState((previous) => ({
      ...previous,
      livePositions: previous.livePositions.map((position) => {
        if (position.id !== positionId) {
          return position
        }

        const delta = direction === 'increase' ? amount : -Math.min(amount, position.stake - 100)
        const stake = clamp(position.stake + delta, 100, 500000)
        const shares = stake / position.entryPrice
        const liquidationValue = shares * position.currentPrice

        return {
          ...position,
          stake,
          shares,
          liquidationValue,
          unrealizedPnl: liquidationValue - stake,
          updatedAt: new Date().toISOString(),
        }
      }),
      liveCashBalance: direction === 'increase' ? previous.liveCashBalance - amount : previous.liveCashBalance + amount,
    }))

    appendLog(
      `${direction === 'increase' ? 'Increased' : 'Reduced'} position ${positionId} by ${Math.round(amount)} USD.`,
      'position-management',
      'info',
      sessionUser.name,
    )
  }

  function markPositionReview(positionId: string) {
    if (!sessionUser) {
      return
    }

    setState((previous) => ({
      ...previous,
      livePositions: previous.livePositions.map((position) =>
        position.id === positionId ? { ...position, status: 'review', updatedAt: new Date().toISOString() } : position,
      ),
    }))

    appendLog(`Marked position ${positionId} for review.`, 'risk-controls', 'warning', sessionUser.name)
  }

  function pauseCategory(category: string) {
    if (!sessionUser) {
      return
    }

    setState((previous) => ({
      ...previous,
      pausedCategories: previous.pausedCategories.includes(category)
        ? previous.pausedCategories
        : [...previous.pausedCategories, category],
    }))

    appendLog(`Paused new entries for ${category}.`, 'risk-controls', 'warning', sessionUser.name)
  }

  function confirmToggleKillSwitch() {
    setPendingKillSwitchAction((current) => !current)
  }

  function executeToggleKillSwitch() {
    setState((previous) => ({
      ...previous,
      killSwitchEnabled: !previous.killSwitchEnabled,
    }))
    setPendingKillSwitchAction(false)
    appendLog(
      `Kill switch ${state.killSwitchEnabled ? 'disabled' : 'enabled'}.`,
      'operations',
      state.killSwitchEnabled ? 'warning' : 'error',
      sessionUser?.name,
    )
  }

  const livePending = state.opportunities.filter((opportunity) => opportunity.currentStage === 'new').length
  const paperPending = state.opportunities.filter((opportunity) => opportunity.currentStage === 'paper').length
  const criticalIssue = state.services.some((service) => service.critical && service.status !== 'healthy')
  const actionBlockedReason = state.killSwitchEnabled
    ? 'Global kill switch is enabled.'
    : criticalIssue
      ? 'Critical services are not fully healthy. Execution is blocked until the backend recovers.'
      : null

  return {
    sessionUser,
    authError,
    signIn,
    createAccount,
    signOut,
    liveSummary: buildSummary('live', state.livePositions, state.liveCashBalance, state.liveRealizedPnl, livePending),
    paperSummary: buildSummary('paper', state.paperPositions, state.paperCashBalance, state.paperRealizedPnl, paperPending),
    opportunities: state.opportunities,
    paperOpportunities: state.opportunities.filter((opportunity) => opportunity.currentStage === 'paper'),
    livePositions: state.livePositions,
    paperPositions: state.paperPositions,
    services: state.services,
    logs: state.logs,
    pausedCategories: state.pausedCategories,
    alerts: buildAlerts(state),
    actionBlockedReason,
    killSwitchEnabled: state.killSwitchEnabled,
    lastRefreshAt: state.lastRefreshAt,
    pendingKillSwitchAction,
    confirmToggleKillSwitch,
    cancelToggleKillSwitch: () => setPendingKillSwitchAction(false),
    executeToggleKillSwitch,
    addOpportunityNote,
    addPositionNote,
    addOpportunityLink,
    addOpportunityFile,
    approveOpportunity,
    rejectOpportunity,
    promotePaperOpportunity,
    closePosition,
    resizePosition,
    markPositionReview,
    pauseCategory,
  }
}
