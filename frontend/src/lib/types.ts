export type NavSection = 'overview' | 'opportunities' | 'positions' | 'paper' | 'operations'
export type ServiceStatus = 'healthy' | 'degraded' | 'down'
export type Environment = 'live' | 'paper'
export type OpportunityStage = 'new' | 'paper' | 'approved' | 'rejected' | 'executed'
export type PositionStatus = 'open' | 'watch' | 'review' | 'paused' | 'closed'
export type NoteContext = 'decision' | 'risk' | 'operations'
export type UserRole = 'trader' | 'analyst' | 'operator'
export type LogLevel = 'info' | 'warning' | 'error'
export type AttachmentType = 'link' | 'file'

export interface UserAccount {
  id: string
  name: string
  email: string
  password: string
  role: UserRole
  createdAt: string
}

export interface SessionUser {
  id: string
  name: string
  email: string
  role: UserRole
}

export interface DecisionNote {
  id: string
  author: string
  createdAt: string
  context: NoteContext
  text: string
}

export interface ResearchAttachment {
  id: string
  type: AttachmentType
  title: string
  url?: string
  fileName?: string
  sizeLabel?: string
  uploadedBy: string
  uploadedAt: string
}

export interface Opportunity {
  id: string
  question: string
  category: string
  marketType: string
  side: 'YES' | 'NO'
  marketProbability: number
  modelProbability: number
  edge: number
  expectedReturn: number
  confidence: number
  liquidity: number
  volume24h: number
  marketDepth: number
  spreadBps: number
  urgencyScore: number
  signalStrength: number
  discoveredAt: string
  lastUpdatedAt: string
  resolutionDate: string
  timeHorizon: string
  recommendedStake: number
  maxStake: number
  entryPriceMin: number
  entryPriceMax: number
  slippageLimitBps: number
  currentStage: OpportunityStage
  statusLabel: string
  strategySummary: string
  thesis: string
  invalidation: string
  riskFlags: string[]
  tags: string[]
  relatedExposure: number
  correlationWarning?: string
  reviewer?: string
  reviewedAt?: string
  priceHistory: number[]
  notes: DecisionNote[]
  attachments: ResearchAttachment[]
}

export interface Position {
  id: string
  opportunityId?: string
  environment: Environment
  question: string
  category: string
  marketType: string
  side: 'YES' | 'NO'
  shares: number
  stake: number
  entryPrice: number
  currentPrice: number
  liquidationValue: number
  unrealizedPnl: number
  status: PositionStatus
  openedAt: string
  updatedAt: string
  modelView: string
  thesisAtEntry: string
  exitGuidance: string
  relatedStrategy: string
  notes: DecisionNote[]
  tags: string[]
  priceHistory: number[]
}

export interface ServiceHealth {
  id: string
  name: string
  description: string
  status: ServiceStatus
  latencyMs: number
  lastHeartbeatAt: string
  owner: string
  critical: boolean
}

export interface LogEvent {
  id: string
  timestamp: string
  level: LogLevel
  source: string
  message: string
  user?: string
  actionRequired?: boolean
}

export interface AlertItem {
  id: string
  tone: 'neutral' | 'warning' | 'critical'
  title: string
  description: string
}

export interface PortfolioSummary {
  environment: Environment
  totalReturnImmediate: number
  openExposure: number
  availableCapital: number
  activePositions: number
  pendingApprovals: number
  realizedPnl: number
  unrealizedPnl: number
  dailyPnl: number
  liquidationValue: number
}

export interface DashboardState {
  liveCashBalance: number
  paperCashBalance: number
  liveRealizedPnl: number
  paperRealizedPnl: number
  opportunities: Opportunity[]
  livePositions: Position[]
  paperPositions: Position[]
  services: ServiceHealth[]
  logs: LogEvent[]
  pausedCategories: string[]
  killSwitchEnabled: boolean
  lastRefreshAt: string
  refreshCount: number
}
