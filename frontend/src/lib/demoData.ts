// Mock data for demo modes: hw6, hw7, hw8.
// Each version builds on the previous one progressively.

import type { DemoVersion } from './demoMode'

// ── Types ──

export type LeaderboardRow = {
  rank: number
  agent_id: string
  name: string
  tier: string
  total_equity: number
  return_pct: number
  sharpe: number | null
  max_drawdown: number
  calmar: number | null
  win_rate: number
  trade_count: number
  status?: string           // hw8: "active" | "paused"
  pause_reason?: string     // hw8: reason for pause
  strategy?: string         // hw7+: strategy name
  overfit_score?: number    // hw8: walk-forward overfit score
}

export type EquityPoint = {
  ts_ms: number
  cash: number
  position_value: number
  total_equity: number
  realized_pnl: number
  unrealized_pnl: number
}

export type ApprovalRequest = {
  id: number
  agent_id: string
  status: 'pending' | 'approved' | 'rejected' | 'revoked'
  requested_at_ms: number
  requested_by: string
  message: string
  reviewed_at_ms: number | null
  confirmation_text: string | null
  max_live_usdc: number | null
  review_message?: string
}

export type SeasonData = {
  id: string
  name: string
  status: 'draft' | 'open_registration' | 'running' | 'settling' | 'finalized'
  starts_at_ms: number
  ends_at_ms: number
  starting_balance: number
  agent_count: number
  mode: string
  market_universe_filter: string
}

export type ExperimentResult = {
  id: string
  title: string
  description: string
  agents_involved: number
  findings: string[]
  metrics: Record<string, string>
}

export type BacktestQueueItem = {
  id: string
  agent_id: string
  strategy: string
  status: 'queued' | 'running' | 'finished' | 'failed'
  enqueued_at_ms: number
  finished_at_ms: number | null
  wait_seconds: number | null
}

export type WalkForwardResult = {
  agent_id: string
  agent_name: string
  in_sample_return: number
  out_of_sample_return: number
  overfit_score: number
  flagged: boolean
}

export type MonteCarloResult = {
  agent_id: string
  agent_name: string
  median_return: number
  ci_low: number
  ci_high: number
  actual_return: number
  within_ci: boolean
  prob_of_ruin: number
}

export type OrderRejection = {
  ts_ms: number
  agent_id: string
  agent_name: string
  order_size: number
  error_code: string
  http_status: number
  message: string
}

export type SafetyEvent = {
  agent_id: string
  agent_name: string
  event: string
  ts_ms: number
  details: string
  duration_ms: number
}

// ── Helpers ──

function ts(daysAgo: number): number {
  return Date.now() - daysAgo * 86400000
}

function generateEquityCurve(
  startBalance: number,
  days: number,
  finalReturn: number,
  volatility: number,
  drawdownAt?: number,   // day index where max drawdown occurs
  maxDd?: number,        // max drawdown fraction
): EquityPoint[] {
  const points: EquityPoint[] = []
  const ticksPerDay = 24 // hourly snapshots
  const totalTicks = days * ticksPerDay
  const dailyReturn = Math.pow(1 + finalReturn, 1 / days) - 1

  let equity = startBalance
  let peak = startBalance
  let cash = startBalance
  let posValue = 0

  for (let i = 0; i <= totalTicks; i++) {
    const day = i / ticksPerDay
    const t = ts(days - day)

    // Apply drawdown dip if specified
    let adjustedReturn = dailyReturn
    if (drawdownAt !== undefined && maxDd !== undefined) {
      const distFromDd = Math.abs(day - drawdownAt)
      if (distFromDd < 2) {
        adjustedReturn = -maxDd / 4 // sharp dip over ~2 days
      } else if (day > drawdownAt && day < drawdownAt + 4) {
        adjustedReturn = dailyReturn * 2 // recovery
      }
    }

    // Add some noise
    const noise = (Math.sin(i * 0.7) * 0.3 + Math.cos(i * 1.3) * 0.2) * volatility
    equity = equity * (1 + adjustedReturn + noise / ticksPerDay)
    if (equity > peak) peak = equity

    // Simulate cash/position split
    const positionRatio = 0.3 + Math.sin(i * 0.1) * 0.15
    posValue = equity * positionRatio
    cash = equity - posValue

    if (i % 4 === 0) { // every 4 hours
      points.push({
        ts_ms: t,
        cash: Math.round(cash * 100) / 100,
        position_value: Math.round(posValue * 100) / 100,
        total_equity: Math.round(equity * 100) / 100,
        realized_pnl: Math.round((equity - startBalance) * 0.6 * 100) / 100,
        unrealized_pnl: Math.round((equity - startBalance) * 0.4 * 100) / 100,
      })
    }
  }
  return points
}

// ── HW6 Data: 1 agent (dashboard agent) ──

const HW6_AGENTS: LeaderboardRow[] = [
  {
    rank: 1,
    agent_id: 'dashboard_agent',
    name: 'Dashboard Agent',
    tier: 'hosted_inprocess',
    total_equity: 10243.18,
    return_pct: 0.0243,
    sharpe: 1.12,
    max_drawdown: 0.032,
    calmar: 0.76,
    win_rate: 0.583,
    trade_count: 24,
    status: 'active',
  },
]

const HW6_APPROVALS: ApprovalRequest[] = []

// ── HW7 Data: 6 agents (2 momentum, 2 mean_reversion, 2 kelly) ──

const HW7_AGENTS: LeaderboardRow[] = [
  {
    rank: 1,
    agent_id: 'kelly_alpha',
    name: 'Kelly Alpha',
    tier: 'hosted_inprocess',
    total_equity: 10892.50,
    return_pct: 0.0893,
    sharpe: 1.42,
    max_drawdown: 0.068,
    calmar: 1.31,
    win_rate: 0.625,
    trade_count: 48,
    status: 'active',
    strategy: 'kelly_sized',
  },
  {
    rank: 2,
    agent_id: 'kelly_beta',
    name: 'Kelly Beta',
    tier: 'hosted_inprocess',
    total_equity: 10741.30,
    return_pct: 0.0741,
    sharpe: 1.38,
    max_drawdown: 0.055,
    calmar: 1.35,
    win_rate: 0.611,
    trade_count: 36,
    status: 'active',
    strategy: 'kelly_sized',
  },
  {
    rank: 3,
    agent_id: 'momentum_alpha',
    name: 'Momentum Alpha',
    tier: 'hosted_inprocess',
    total_equity: 10945.00,
    return_pct: 0.0945,
    sharpe: 0.89,
    max_drawdown: 0.143,
    calmar: 0.66,
    win_rate: 0.538,
    trade_count: 65,
    status: 'active',
    strategy: 'momentum',
  },
  {
    rank: 4,
    agent_id: 'momentum_beta',
    name: 'Momentum Beta',
    tier: 'hosted_inprocess',
    total_equity: 10698.00,
    return_pct: 0.0698,
    sharpe: 0.82,
    max_drawdown: 0.129,
    calmar: 0.54,
    win_rate: 0.512,
    trade_count: 58,
    status: 'active',
    strategy: 'momentum',
  },
  {
    rank: 5,
    agent_id: 'meanrev_alpha',
    name: 'MeanRev Alpha',
    tier: 'hosted_inprocess',
    total_equity: 10012.40,
    return_pct: 0.0012,
    sharpe: 0.15,
    max_drawdown: 0.008,
    calmar: 0.15,
    win_rate: 0.500,
    trade_count: 4,
    status: 'active',
    strategy: 'mean_reversion',
  },
  {
    rank: 6,
    agent_id: 'meanrev_beta',
    name: 'MeanRev Beta',
    tier: 'hosted_inprocess',
    total_equity: 9998.70,
    return_pct: -0.0001,
    sharpe: -0.05,
    max_drawdown: 0.005,
    calmar: null,
    win_rate: 0.333,
    trade_count: 3,
    status: 'active',
    strategy: 'mean_reversion',
  },
]

const HW7_EXPERIMENTS: ExperimentResult[] = [
  {
    id: 'exp1',
    title: 'Experiment 1: Strategy Comparison (Momentum vs Mean Reversion vs Kelly)',
    description: '6 agents — 2 per strategy — traded the same 10-market NBA universe over a simulated 2-week window. Each agent ran a backtest first, then placed paper trades based on results.',
    agents_involved: 6,
    findings: [
      'Momentum agents produced highest raw return (+8.2% avg) but worst max drawdown (-14.3%)',
      'Kelly-sized agents had best Sharpe ratio (1.42 vs 0.89 for momentum) — Kelly naturally sizes down when edge is uncertain',
      'Mean reversion agents barely traded — prediction markets don\'t mean-revert like equities, generating almost no signals',
      'Composite leaderboard ranked Kelly agents #1 and #2',
    ],
    metrics: {
      'Momentum Avg Return': '+8.2%',
      'Momentum Max DD': '-14.3%',
      'Kelly Sharpe': '1.42',
      'Mean Rev Trades': '3-4 total',
    },
  },
  {
    id: 'exp2',
    title: 'Experiment 2: Risk Gate Tier Enforcement',
    description: '3 agents as external_http (max order 500 USDC, max position 2000 USDC) and 3 as hosted_inprocess (5000/10000). All 6 attempted identical 800 USDC orders.',
    agents_involved: 6,
    findings: [
      'External agents correctly rejected with risk_gate.max_order_size (403 with structured error)',
      'In-process agents filled successfully at 800 USDC',
      '100% of risk gate violations caught, zero false positives',
      'Structured error contract gave agents enough info to self-correct (reduce order size)',
    ],
    metrics: {
      'Violations Caught': '100%',
      'False Positives': '0',
      'Error Code': 'risk_gate.max_order_size',
      'HTTP Status': '403',
    },
  },
  {
    id: 'exp3',
    title: 'Experiment 3: Backtest Queue Under Concurrent Load',
    description: '12 backtest jobs submitted simultaneously from 6 agents (2 per agent) to test the SKIP LOCKED queue.',
    agents_involved: 6,
    findings: [
      'All 12 jobs completed with no duplicate claims and FIFO ordering',
      'Average queue wait was 4.2 seconds (2s poll interval x ~2 jobs ahead)',
      'No lost jobs, no duplicate processing',
      'Quota gate correctly rejected 13th job from agent at max_concurrent=2 limit (429)',
    ],
    metrics: {
      'Jobs Submitted': '12',
      'Jobs Completed': '12',
      'Avg Queue Wait': '4.2s',
      'Duplicates': '0',
    },
  },
]

// Wait times: [1.1, 2.0, 2.5, 3.2, 3.5, 4.0, 4.4, 4.8, 5.2, 5.6, 6.1, 8.0] → avg = 4.2s
const HW7_BACKTEST_QUEUE: BacktestQueueItem[] = [
  { id: 'bt-001', agent_id: 'kelly_alpha', strategy: 'kelly_sized', status: 'finished', enqueued_at_ms: ts(13.9), finished_at_ms: ts(13.88), wait_seconds: 1.1 },
  { id: 'bt-002', agent_id: 'kelly_alpha', strategy: 'kelly_sized', status: 'finished', enqueued_at_ms: ts(13.89), finished_at_ms: ts(13.85), wait_seconds: 2.0 },
  { id: 'bt-003', agent_id: 'kelly_beta', strategy: 'kelly_sized', status: 'finished', enqueued_at_ms: ts(13.88), finished_at_ms: ts(13.84), wait_seconds: 2.5 },
  { id: 'bt-004', agent_id: 'kelly_beta', strategy: 'kelly_sized', status: 'finished', enqueued_at_ms: ts(13.87), finished_at_ms: ts(13.82), wait_seconds: 3.2 },
  { id: 'bt-005', agent_id: 'momentum_alpha', strategy: 'momentum', status: 'finished', enqueued_at_ms: ts(13.86), finished_at_ms: ts(13.81), wait_seconds: 3.5 },
  { id: 'bt-006', agent_id: 'momentum_alpha', strategy: 'momentum', status: 'finished', enqueued_at_ms: ts(13.85), finished_at_ms: ts(13.79), wait_seconds: 4.0 },
  { id: 'bt-007', agent_id: 'momentum_beta', strategy: 'momentum', status: 'finished', enqueued_at_ms: ts(13.84), finished_at_ms: ts(13.78), wait_seconds: 4.4 },
  { id: 'bt-008', agent_id: 'momentum_beta', strategy: 'momentum', status: 'finished', enqueued_at_ms: ts(13.83), finished_at_ms: ts(13.76), wait_seconds: 4.8 },
  { id: 'bt-009', agent_id: 'meanrev_alpha', strategy: 'mean_reversion', status: 'finished', enqueued_at_ms: ts(13.82), finished_at_ms: ts(13.75), wait_seconds: 5.2 },
  { id: 'bt-010', agent_id: 'meanrev_alpha', strategy: 'mean_reversion', status: 'finished', enqueued_at_ms: ts(13.81), finished_at_ms: ts(13.73), wait_seconds: 5.6 },
  { id: 'bt-011', agent_id: 'meanrev_beta', strategy: 'mean_reversion', status: 'finished', enqueued_at_ms: ts(13.80), finished_at_ms: ts(13.72), wait_seconds: 6.1 },
  { id: 'bt-012', agent_id: 'meanrev_beta', strategy: 'mean_reversion', status: 'finished', enqueued_at_ms: ts(13.79), finished_at_ms: ts(13.70), wait_seconds: 8.0 },
  // 13th job: rejected by quota gate (max_concurrent=2)
  { id: 'bt-013', agent_id: 'kelly_alpha', strategy: 'kelly_sized', status: 'failed', enqueued_at_ms: ts(13.78), finished_at_ms: null, wait_seconds: null },
]

const HW7_RISK_GATE_LOG = [
  { agent_id: 'ext_agent_1', tier: 'external_http', order_size: 800, limit: 500, result: 'REJECTED', code: 'risk_gate.max_order_size', http: 403 },
  { agent_id: 'ext_agent_2', tier: 'external_http', order_size: 800, limit: 500, result: 'REJECTED', code: 'risk_gate.max_order_size', http: 403 },
  { agent_id: 'ext_agent_3', tier: 'external_http', order_size: 800, limit: 500, result: 'REJECTED', code: 'risk_gate.max_order_size', http: 403 },
  { agent_id: 'momentum_alpha', tier: 'hosted_inprocess', order_size: 800, limit: 5000, result: 'FILLED', code: '', http: 200 },
  { agent_id: 'momentum_beta', tier: 'hosted_inprocess', order_size: 800, limit: 5000, result: 'FILLED', code: '', http: 200 },
  { agent_id: 'kelly_alpha', tier: 'hosted_inprocess', order_size: 800, limit: 5000, result: 'FILLED', code: '', http: 200 },
]

// ── HW8 Data: 30 agents + seasons + safety ──

function generateHw8Agents(): LeaderboardRow[] {
  const strategies = ['momentum', 'kelly_sized', 'fade_longshot', 'threshold', 'pendulum', 'nothing_happens']
  void strategies // used below in loops

  const agents: LeaderboardRow[] = []

  // 5 momentum variants (hosted_inprocess)
  const momentumNames = ['Momentum-3tick', 'Momentum-5tick', 'Momentum-7tick', 'Momentum-10tick', 'Momentum-15tick']
  const momentumReturns = [0.051, 0.068, 0.091, 0.072, 0.043]
  const momentumSharpes = [0.72, 0.85, 1.05, 0.89, 0.61]
  for (let i = 0; i < 5; i++) {
    agents.push({
      rank: 0, agent_id: `momentum_${i+1}`, name: momentumNames[i], tier: 'hosted_inprocess',
      total_equity: 10000 * (1 + momentumReturns[i]),
      return_pct: momentumReturns[i], sharpe: momentumSharpes[i],
      max_drawdown: 0.08 + Math.random() * 0.08,
      calmar: momentumSharpes[i] * 0.7,
      win_rate: 0.48 + Math.random() * 0.12,
      trade_count: 150 + Math.floor(Math.random() * 100),
      status: 'active', strategy: 'momentum',
    })
  }

  // 3 kelly variants (hosted_inprocess)
  const kellyNames = ['Kelly-Quarter', 'Kelly-Half', 'Kelly-3x']
  const kellyReturns = [0.082, 0.105, -0.31]  // 3x Kelly blows up
  const kellySharpes = [1.45, 1.22, -0.85]
  for (let i = 0; i < 3; i++) {
    agents.push({
      rank: 0, agent_id: `kelly_${i+1}`, name: kellyNames[i], tier: 'hosted_inprocess',
      total_equity: 10000 * (1 + kellyReturns[i]),
      return_pct: kellyReturns[i], sharpe: kellySharpes[i],
      max_drawdown: i === 2 ? 0.31 : 0.04 + Math.random() * 0.04,
      calmar: i === 2 ? -1.0 : kellySharpes[i] * 0.8,
      win_rate: i === 2 ? 0.35 : 0.60 + Math.random() * 0.05,
      trade_count: 80 + Math.floor(Math.random() * 60),
      status: i === 2 ? 'paused' : 'active',
      pause_reason: i === 2 ? 'Drawdown breaker triggered at -31%. Equity dropped below 70% of starting balance.' : undefined,
      strategy: 'kelly_sized',
    })
  }

  // 2 fade longshot (hosted_inprocess)
  for (let i = 0; i < 2; i++) {
    const ret = 0.03 + Math.random() * 0.04
    agents.push({
      rank: 0, agent_id: `fade_${i+1}`, name: `Fade-Longshot-${i+1}`, tier: 'hosted_inprocess',
      total_equity: 10000 * (1 + ret), return_pct: ret, sharpe: 0.9 + Math.random() * 0.4,
      max_drawdown: 0.03 + Math.random() * 0.03, calmar: 1.1 + Math.random() * 0.5,
      win_rate: 0.55 + Math.random() * 0.1, trade_count: 60 + Math.floor(Math.random() * 40),
      status: 'active', strategy: 'fade_longshot',
    })
  }

  // 12 external HTTP agents
  const extStrategies = ['momentum', 'kelly_sized', 'threshold', 'pendulum', 'fade_longshot', 'nothing_happens']
  for (let i = 0; i < 12; i++) {
    const strat = extStrategies[i % extStrategies.length]
    const ret = -0.05 + Math.random() * 0.15
    const sh = -0.3 + Math.random() * 2.0
    agents.push({
      rank: 0, agent_id: `ext_http_${i+1}`, name: `ExtAgent-${i+1}`, tier: 'external_http',
      total_equity: 10000 * (1 + ret), return_pct: ret, sharpe: sh,
      max_drawdown: 0.02 + Math.random() * 0.1, calmar: sh > 0 ? sh * 0.6 : null,
      win_rate: 0.35 + Math.random() * 0.25, trade_count: 100 + Math.floor(Math.random() * 200),
      status: 'active', strategy: strat,
    })
  }

  // 8 MCP agents
  for (let i = 0; i < 8; i++) {
    const strat = strategies[i % strategies.length]
    const ret = -0.03 + Math.random() * 0.12
    const sh = -0.2 + Math.random() * 1.8
    agents.push({
      rank: 0, agent_id: `mcp_agent_${i+1}`, name: `MCP-Claude-${i+1}`, tier: 'external_mcp',
      total_equity: 10000 * (1 + ret), return_pct: ret, sharpe: sh,
      max_drawdown: 0.02 + Math.random() * 0.08, calmar: sh > 0 ? sh * 0.5 : null,
      win_rate: 0.40 + Math.random() * 0.2, trade_count: 50 + Math.floor(Math.random() * 150),
      status: 'active', strategy: strat,
    })
  }

  // Sort by return descending and assign ranks
  agents.sort((a, b) => b.return_pct - a.return_pct)
  agents.forEach((a, i) => {
    a.rank = i + 1
    // Round numeric fields
    a.total_equity = Math.round(a.total_equity * 100) / 100
    a.return_pct = Math.round(a.return_pct * 10000) / 10000
    a.sharpe = a.sharpe !== null ? Math.round(a.sharpe * 100) / 100 : null
    a.max_drawdown = Math.round(a.max_drawdown * 10000) / 10000
    a.calmar = a.calmar !== null ? Math.round(a.calmar * 100) / 100 : null
    a.win_rate = Math.round(a.win_rate * 1000) / 1000
  })

  return agents
}

// Cache so it's stable across renders
let _hw8Agents: LeaderboardRow[] | null = null
function getHw8Agents(): LeaderboardRow[] {
  if (!_hw8Agents) _hw8Agents = generateHw8Agents()
  return _hw8Agents
}

const HW8_SEASON: SeasonData = {
  id: 'season_stress_test',
  name: 'Stress Test Season',
  status: 'finalized',
  starts_at_ms: ts(14),
  ends_at_ms: ts(0),
  starting_balance: 10000,
  agent_count: 30,
  mode: 'paper',
  market_universe_filter: 'NBA only',
}

const HW8_WALK_FORWARD: WalkForwardResult[] = [
  { agent_id: 'ext_http_3', agent_name: 'ExtAgent-3', in_sample_return: 0.152, out_of_sample_return: -0.031, overfit_score: 0.78, flagged: true },
  { agent_id: 'ext_http_7', agent_name: 'ExtAgent-7', in_sample_return: 0.148, out_of_sample_return: -0.028, overfit_score: 0.74, flagged: true },
  { agent_id: 'mcp_agent_4', agent_name: 'MCP-Claude-4', in_sample_return: 0.161, out_of_sample_return: -0.035, overfit_score: 0.82, flagged: true },
  { agent_id: 'kelly_1', agent_name: 'Kelly-Quarter', in_sample_return: 0.095, out_of_sample_return: 0.082, overfit_score: 0.12, flagged: false },
  { agent_id: 'momentum_3', agent_name: 'Momentum-7tick', in_sample_return: 0.102, out_of_sample_return: 0.091, overfit_score: 0.09, flagged: false },
]

// Deterministic seeded random for stable demo data
function seededRandom(seed: number): () => number {
  let s = seed
  return () => {
    s = (s * 16807 + 0) % 2147483647
    return s / 2147483647
  }
}

function generateMonteCarloResults(): MonteCarloResult[] {
  const agents = getHw8Agents()
  const rng = seededRandom(42)

  // Exactly 3 agents will be outside CI (indices 5, 14, 22) → 27/30 within
  const outsideCiIndices = new Set([5, 14, 22])

  return agents.map((a, i) => {
    const spread = 0.03 + rng() * 0.05
    const isOutside = outsideCiIndices.has(i)

    let ciLow: number, ciHigh: number
    if (isOutside) {
      // Shift CI so actual return falls outside it
      const shift = spread * 1.5
      ciLow = a.return_pct + shift * 0.2
      ciHigh = a.return_pct + shift * 0.2 + spread * 2
    } else {
      ciLow = a.return_pct - spread
      ciHigh = a.return_pct + spread
    }

    const withinCi = a.return_pct >= ciLow && a.return_pct <= ciHigh

    return {
      agent_id: a.agent_id,
      agent_name: a.name,
      median_return: a.return_pct + (rng() - 0.5) * 0.01,
      ci_low: Math.round(ciLow * 10000) / 10000,
      ci_high: Math.round(ciHigh * 10000) / 10000,
      actual_return: a.return_pct,
      within_ci: withinCi,
      prob_of_ruin: a.return_pct < -0.1 ? 0.15 + rng() * 0.2 : rng() * 0.05,
    }
  })
}

let _hw8MonteCarlo: MonteCarloResult[] | null = null
function getMonteCarloResults(): MonteCarloResult[] {
  if (!_hw8MonteCarlo) _hw8MonteCarlo = generateMonteCarloResults()
  return _hw8MonteCarlo
}

const HW8_APPROVALS: ApprovalRequest[] = [
  {
    id: 1, agent_id: 'kelly_3', status: 'revoked',
    requested_at_ms: ts(10), requested_by: 'kelly_3',
    message: 'Requesting live trading access — strong backtest results',
    reviewed_at_ms: ts(7), confirmation_text: null, max_live_usdc: null,
    review_message: 'Auto-revoked: drawdown breaker triggered at -31%',
  },
  {
    id: 2, agent_id: 'kelly_1', status: 'pending',
    requested_at_ms: ts(3), requested_by: 'kelly_1',
    message: 'Kelly-Quarter requesting live promotion — Sharpe 1.45, max DD 4.2%',
    reviewed_at_ms: null, confirmation_text: null, max_live_usdc: null,
  },
  {
    id: 3, agent_id: 'momentum_3', status: 'pending',
    requested_at_ms: ts(2), requested_by: 'momentum_3',
    message: 'Momentum-7tick — best param search result, requesting live access',
    reviewed_at_ms: null, confirmation_text: null, max_live_usdc: null,
  },
]

// Order rejections after Kelly-3x was paused
const HW8_ORDER_REJECTIONS: OrderRejection[] = [
  { ts_ms: ts(5.1), agent_id: 'kelly_3', agent_name: 'Kelly-3x', order_size: 1200, error_code: 'risk_gate.agent_paused', http_status: 403, message: 'Agent is paused due to drawdown breaker. Contact admin to resume.' },
  { ts_ms: ts(4.9), agent_id: 'kelly_3', agent_name: 'Kelly-3x', order_size: 800, error_code: 'risk_gate.agent_paused', http_status: 403, message: 'Agent is paused due to drawdown breaker. Contact admin to resume.' },
  { ts_ms: ts(4.7), agent_id: 'kelly_3', agent_name: 'Kelly-3x', order_size: 500, error_code: 'risk_gate.agent_paused', http_status: 403, message: 'Agent is paused due to drawdown breaker. Contact admin to resume.' },
]

// Safety event timeline
const HW8_SAFETY_EVENTS: SafetyEvent[] = [
  { agent_id: 'kelly_3', agent_name: 'Kelly-3x', event: 'Drawdown breaker triggered', ts_ms: ts(6), details: 'Equity dropped to $6,900 (31% below $10,000 starting balance). Threshold: 70%.', duration_ms: 0 },
  { agent_id: 'kelly_3', agent_name: 'Kelly-3x', event: 'Agent status set to PAUSED', ts_ms: ts(6) + 1200, details: 'Status flipped from active to paused. All pending orders cancelled.', duration_ms: 1200 },
  { agent_id: 'kelly_3', agent_name: 'Kelly-3x', event: 'Live access revoked (kill switch)', ts_ms: ts(6) + 4800, details: 'Approval revoked via DELETE /api/v1/agents/kelly_3/live. Total time: 4.8 seconds.', duration_ms: 4800 },
  { agent_id: 'kelly_3', agent_name: 'Kelly-3x', event: 'Subsequent orders blocked', ts_ms: ts(5.1), details: '3 order attempts rejected with risk_gate.agent_paused (403).', duration_ms: 0 },
]

// ── Demo backtest result (pre-baked for all HW versions) ──

function generateDemoBacktestResult(): any {
  const startCash = 10000
  const curve: { timestamp: number; cash: number; position_value: number; total_equity: number }[] = []
  let equity = startCash
  for (let i = 0; i < 200; i++) {
    equity = equity * (1 + (Math.sin(i * 0.15) * 0.003 + 0.001))
    const posRatio = 0.25 + Math.sin(i * 0.08) * 0.1
    curve.push({
      timestamp: 1700000000 + i * 3600,
      cash: equity * (1 - posRatio),
      position_value: equity * posRatio,
      total_equity: equity,
    })
  }
  const endEquity = curve[curve.length - 1].total_equity
  const totalReturn = ((endEquity - startCash) / startCash) * 100

  const trades = [
    { timestamp: 1700003600, token_id: 't1', market_id: 'm1', market_question: 'Will the Lakers win the NBA Finals?', outcome: 'Yes', side: 'BUY', price: 0.42, shares: 238, cost: 100, fee: 0.5, reason: 'Momentum signal: short MA crossed above long MA' },
    { timestamp: 1700010800, token_id: 't1', market_id: 'm1', market_question: 'Will the Lakers win the NBA Finals?', outcome: 'Yes', side: 'SELL', price: 0.48, shares: 238, cost: 114.24, fee: 0.57, reason: 'Take profit: price rose above exit threshold' },
    { timestamp: 1700025200, token_id: 't2', market_id: 'm2', market_question: 'Will the Celtics win 60+ games?', outcome: 'Yes', side: 'BUY', price: 0.35, shares: 285, cost: 100, fee: 0.5, reason: 'Momentum signal: short MA crossed above long MA' },
    { timestamp: 1700046800, token_id: 't2', market_id: 'm2', market_question: 'Will the Celtics win 60+ games?', outcome: 'Yes', side: 'SELL', price: 0.31, shares: 285, cost: 88.35, fee: 0.44, reason: 'Stop loss: price dropped below entry' },
    { timestamp: 1700068400, token_id: 't3', market_id: 'm3', market_question: 'Will Jokic win MVP?', outcome: 'Yes', side: 'BUY', price: 0.55, shares: 181, cost: 100, fee: 0.5, reason: 'Kelly edge detected: model p=0.62 vs market p=0.55' },
    { timestamp: 1700100000, token_id: 't3', market_id: 'm3', market_question: 'Will Jokic win MVP?', outcome: 'Yes', side: 'SELL', price: 0.61, shares: 181, cost: 110.41, fee: 0.55, reason: 'Take profit: edge narrowed below threshold' },
  ]

  return {
    backtest_id: 'demo-bt-001',
    strategy_name: 'momentum',
    starting_cash: startCash,
    ending_cash: endEquity * 0.65,
    ending_equity: endEquity,
    fee_bps: 50,
    fidelity: 60,
    markets: ['Lakers NBA Finals', 'Celtics 60+ wins', 'Jokic MVP'],
    strategy_params: { short_window: 10, long_window: 40 },
    metrics: {
      total_return_pct: totalReturn,
      total_return_usd: endEquity - startCash,
      sharpe_ratio: 1.18,
      max_drawdown_pct: 3.2,
      max_drawdown_usd: 320,
      win_rate: 0.667,
      profit_factor: 2.15,
      avg_trade_pnl: 8.1,
      total_trades: 6,
      winning_trades: 4,
      losing_trades: 2,
      avg_win: 12.5,
      avg_loss: -8.3,
      best_trade_pnl: 14.24,
      worst_trade_pnl: -11.65,
      total_fees_paid: 3.06,
    },
    trades,
    equity_curve: curve,
  }
}

let _demoBacktest: any = null
export function getDemoBacktestResult(): any {
  if (!_demoBacktest) _demoBacktest = generateDemoBacktestResult()
  return _demoBacktest
}

// HW6 system info (API endpoints, auth, etc.)
export const HW6_SYSTEM_INFO = {
  endpoints: [
    { method: 'POST', path: '/api/v1/orders', description: 'Place an order (MARKET or LIMIT)' },
    { method: 'DELETE', path: '/api/v1/orders/:id', description: 'Cancel pending limit order' },
    { method: 'GET', path: '/api/v1/orders/:id/explain', description: 'Get audit trail + orderbook snapshot' },
    { method: 'GET', path: '/api/v1/portfolio', description: 'Get agent portfolio summary' },
    { method: 'GET', path: '/api/v1/positions', description: 'List open positions' },
    { method: 'GET', path: '/api/v1/balance', description: 'Get cash balance' },
    { method: 'GET', path: '/api/v1/trades', description: 'Get trade history' },
    { method: 'GET', path: '/api/v1/leaderboard', description: 'Global leaderboard' },
    { method: 'POST', path: '/api/v1/backtest', description: 'Enqueue async backtest job' },
    { method: 'GET', path: '/api/v1/backtest/:id', description: 'Poll backtest status/result' },
    { method: 'GET', path: '/api/v1/quota', description: 'Check agent trading/backtest limits' },
  ],
  auth: {
    type: 'Bearer Token',
    flow: 'AgentRegistry.issue_key() → SHA256 hash stored → plain token returned once',
    header: 'Authorization: Bearer <token>',
  },
  tests: {
    total: 65,
    framework: 'pytest + testcontainers',
    databases: ['SQLite (dev)', 'Postgres (prod)'],
    key_test: 'Golden-file replay: 10-order session on 2 DBs, byte-identical diff',
  },
  audit: {
    fields: ['orderbook_snapshot_id', 'request_hash', 'response_hash', 'price_tick_id'],
    storage: 'audit_log table with request_id correlation',
    replay: 'Byte-identical replay via golden-file tests',
  },
  deployment: {
    frontend: 'Vercel (React + Vite)',
    backend: 'Vercel Serverless (Flask)',
    worker: 'Railway (background backtest worker + portfolio sampler)',
    database: 'Supabase Postgres',
  },
}

// ── Public API ──

export function getDemoAgents(version: DemoVersion): LeaderboardRow[] {
  switch (version) {
    case 'hw6': return HW6_AGENTS
    case 'hw7': return HW7_AGENTS
    case 'hw8': return getHw8Agents()
    default: return []
  }
}

export function getDemoEquityCurve(version: DemoVersion, agentId: string): EquityPoint[] {
  const agents = getDemoAgents(version)
  const agent = agents.find(a => a.agent_id === agentId)
  if (!agent) return []

  const days = version === 'hw6' ? 7 : 14
  const ddDay = agent.status === 'paused' ? 9 : undefined
  const maxDd = agent.status === 'paused' ? agent.max_drawdown : undefined

  return generateEquityCurve(
    10000, days, agent.return_pct, 0.005,
    ddDay, maxDd,
  )
}

export function getDemoApprovals(version: DemoVersion): ApprovalRequest[] {
  switch (version) {
    case 'hw6': return HW6_APPROVALS
    case 'hw7': return []
    case 'hw8': return HW8_APPROVALS
    default: return []
  }
}

export function getDemoExperiments(): ExperimentResult[] {
  return HW7_EXPERIMENTS
}

export function getDemoBacktestQueue(): BacktestQueueItem[] {
  return HW7_BACKTEST_QUEUE
}

export function getDemoRiskGateLog() {
  return HW7_RISK_GATE_LOG
}

export function getDemoSeason(): SeasonData {
  return HW8_SEASON
}

export function getDemoWalkForward(): WalkForwardResult[] {
  return HW8_WALK_FORWARD
}

export function getDemoMonteCarlo(): MonteCarloResult[] {
  return getMonteCarloResults()
}

export function getDemoOrderRejections(): OrderRejection[] {
  return HW8_ORDER_REJECTIONS
}

export function getDemoSafetyEvents(): SafetyEvent[] {
  return HW8_SAFETY_EVENTS
}

export function getDemoStats(version: DemoVersion) {
  const agents = getDemoAgents(version)
  const totalEquity = agents.reduce((s, a) => s + a.total_equity, 0)
  const totalTrades = agents.reduce((s, a) => s + a.trade_count, 0)
  const avgReturn = agents.reduce((s, a) => s + a.return_pct, 0) / agents.length
  const pausedCount = agents.filter(a => a.status === 'paused').length

  return {
    agentCount: agents.length,
    totalEquity,
    totalTrades,
    avgReturn,
    pausedCount,
    activeCount: agents.length - pausedCount,
  }
}
