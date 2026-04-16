# PLAN V2: PolyClaw-Agentic — Next Roadmap (Phases 4-7)

**Author:** drafted 2026-04-15, post-Phase-3 merge  
**Builds on:** Phases 0-3 shipped (6 PRs, 65 tests, 12 tables, 11 API routes)

---

## What's shipped (Phase 0-3 recap)

| Phase | What | LOC delta | Tests |
|-------|------|-----------|-------|
| 0 | Hygiene, dedup, CI, production guard | ~200 | 6 |
| 1 | Multi-tenant PaperTrader, Decimal, Clock, replay invariant | ~1500 | 10 |
| 2a | price_ticks, PriceTickIngester, PostgresSource | ~900 | 7 |
| 2b | AgentRegistry, TradingService, arena deletion | ~800 | 11 |
| 2c | BacktestQueue (SKIP LOCKED), worker, sampler | ~700 | 16 |
| 3a | /api/v1 Blueprint, auth middleware, RiskGate | ~600 | 15 |
| 3b | polyclaw-agent-sdk, 5 cookbook examples, CLI scaffolder | ~850 | 0 (sdk) |
| 3c | MCP server, docker-compose, README | ~470 | 0 (infra) |

**What an agent can do today:** register → get bearer token → browse leaderboard → enqueue backtests → place paper trades → check portfolio → check quota → explain any trade's audit trail → run all of this via SDK or MCP.

**What's missing (the gaps that drive V2):**

1. **No seasons.** Agents trade in an infinite sandbox with no start/end, no competitive ranking, no reset cadence. There's nothing to "win."
2. **Backtesting is basic.** 7 strategies, all built-in. No custom strategy upload, no walk-forward analysis, no Monte Carlo, no parameter optimization. Professional platforms (QuantConnect, Zipline, Backtrader) offer all of these.
3. **No visualization for humans.** The frontend is 4 pages, only one (the leaderboard) is Phase 2b+ wired. There's no equity curve view, no trade timeline, no risk dashboard, no way for an agent to "present its case" to a human.
4. **No human approval workflow.** PLAN.md premise P1 says "paper is a tier; live is the north star." But there's no mechanism for a human to review an agent's track record and authorize live trading.
5. **The UI is developer-facing, not human-facing.** It's a debug dashboard. It needs to become a product a non-technical person could use to monitor their agents.

---

## Vision restatement

An **agentic trading platform** where:

- AI agents independently research, backtest, and paper-trade Polymarket prediction markets
- Agents compete on risk-adjusted PnL within structured seasons
- **Agents generate rich visualizations** (equity curves, risk reports, strategy explanations) that they present to their human owner
- **Humans review agent performance** via a polished UI: leaderboard, per-agent dashboards, risk metrics, trade history
- **Humans approve agents to trade real money** once satisfied with paper performance — a gated promotion from `paper` → `live` tier with signed confirmation and explicit risk acknowledgment

---

## Phase 4 — Season engine + composite leaderboard

**Goal:** Give agents something to compete for. Structured time windows with rankings.

### 4.1 Seasons table + lifecycle

- `seasons(id, name, starts_at, ends_at, starting_balance, market_universe_filter, mode, allowed_lookback_days, max_order_rate_per_min, max_position_size_usdc, registration_open, status)`
- Lifecycle: `draft → open_registration → running → settling → finalized`
- Worker loop: at `starts_at` freeze registration and snapshot starting balances. At `ends_at` mark-to-market all positions using last `market_snapshots`, compute final rankings, write `season_results`.
- Reset: new season = fresh portfolios (agent persists, balance resets).

### 4.2 Composite leaderboard metrics

Upgrade the scaffold `/api/v1/leaderboard` to compute **from `portfolio_snapshots`**:

| Metric | Source | Weight in composite |
|--------|--------|-------------------|
| Total return % | equity curve | 35% |
| Sharpe ratio | daily returns | 25% |
| Max drawdown % | equity curve | 15% |
| Calmar ratio | return / max DD | 10% |
| Win rate | paper_trades | 10% |
| Trade count (anti-dust) | paper_trades | 5% |

Reuse `src/polyclaw/backtest/metrics.py` — it already computes Sharpe, drawdown, win rate for backtests. Lift it to work on `portfolio_snapshots` time series.

### 4.3 Always-on sandbox season

A permanent `sandbox-historical` season backed by a frozen 2-week historical tick window. New devs register any day, trade against historical data via the replay-mode `MarketDataProvider`, see themselves on a sandbox leaderboard. Resets weekly. Not comparable to real seasons, clearly tagged.

### 4.4 Season admin API

- `POST /api/v1/seasons` (admin) — create
- `PATCH /api/v1/seasons/:id` (admin) — transition lifecycle
- `GET /api/v1/seasons` — list
- `GET /api/v1/seasons/:id` — details + results

### 4.5 First real season

"May 2026 NBA Playoffs" — 2-week window, $10k starting balance, NBA-only markets. 3 house agents (`baseline_kelly`, `momentum_bot`, `llm_claude_bot`) seeded as benchmarks.

**Tests:** season lifecycle transitions, composite metric computation, sandbox reset, mark-to-market at end.

---

## Phase 5 — Industry-grade backtesting

**Goal:** Match what professional platforms offer so agents can do real research.

### 5.1 What sophisticated platforms have that we don't

| Feature | QuantConnect | Zipline | Backtrader | PolyClaw today |
|---------|-------------|---------|------------|----------------|
| Walk-forward analysis | Yes | No | Yes | No |
| Monte Carlo simulation | Yes | No | Plugin | No |
| Parameter optimization | Yes | Partial | Yes | No |
| Custom strategy upload | Yes (C#/Python) | Yes (Python) | Yes (Python) | No |
| Multi-timeframe analysis | Yes | Yes | Yes | No |
| Slippage models | Configurable | Basic | Configurable | Fixed (orderbook walk) |
| Commission models | Configurable | Configurable | Configurable | Fixed (CLOB fee rate) |
| Risk-of-ruin analysis | Yes | No | No | No |
| Strategy combination / ensemble | Yes | No | Yes | No |
| Correlation analysis (between strategies) | Yes | No | No | No |

### 5.2 What we'll build (prioritized by agent value)

**5.2a — Walk-forward analysis** (critical for avoiding overfitting)
- Split price_ticks into in-sample and out-of-sample windows
- Run backtest on in-sample, validate on out-of-sample
- API: `POST /api/v1/backtest` gains `walk_forward: {train_pct: 0.7, n_splits: 5}`
- Result includes per-split metrics + aggregate + overfit score

**5.2b — Monte Carlo simulation** (confidence intervals on strategy returns)
- Bootstrap resample trades from a backtest result 1000 times
- Report: median return, 5th/95th percentile, probability of ruin
- API: `POST /api/v1/backtest` gains `monte_carlo: {n_simulations: 1000}`
- Result includes distribution histogram data the frontend can chart

**5.2c — Parameter optimization** (grid search / random search)
- Agent specifies strategy + param ranges → queue runs N backtests
- Returns parameter heat map (which combos performed best)
- API: `POST /api/v1/backtest/optimize` with `{strategy, param_grid: {window: [10,20,30], threshold: [0.3,0.5,0.7]}}`
- Cap: 100 combinations per run (quota enforced)

**5.2d — Custom strategy upload** (sandboxed Python execution)
- Agent uploads a Python file implementing `Strategy` ABC
- Executed in a WebAssembly sandbox (Pyodide) or subprocess with `--no-network` + resource limits
- Strategy gets `TickContext` with price, position, cash — same interface as built-in strategies
- API: `POST /api/v1/strategies/upload` → returns strategy_id; usable in backtest enqueue

**5.2e — Strategy ensemble / combination**
- Run N strategies on the same market, combine signals (majority vote, weighted average, etc.)
- API: `POST /api/v1/backtest` gains `ensemble: [{strategy: "momentum", weight: 0.6}, {strategy: "mean_reversion", weight: 0.4}]`

**Tests:** walk-forward overfit detection on known overfitting strategy, Monte Carlo convergence, param grid quota enforcement, sandboxed strategy isolation (no network, no filesystem escape).

---

## Phase 6 — Visualization + human-facing UI

**Goal:** Make the platform a product a human can use, not a developer debug tool.

### 6.1 Design principles

- **Agent-centric, not trade-centric.** The primary object is "my agent" — its equity curve, its risk profile, its strategy. Individual trades are drill-downs.
- **Temporal.** Everything should be scrubable on a timeline. "What was my agent doing on April 10th?"
- **Comparative.** Humans want to see their agent vs the field. Side-by-side equity curves, relative Sharpe.
- **Actionable.** Every screen leads to a next step: "approve for live", "pause this agent", "run a deeper backtest", "review the worst trade."

### 6.2 Pages

**a) Dashboard (home)** — `/`
- Season summary: current season name, days remaining, your rank
- Agent cards: one per registered agent showing equity sparkline, return %, Sharpe
- Quick actions: "run backtest", "view leaderboard", "register new agent"

**b) Agent detail** — `/agents/:id`
- Hero section: equity curve (interactive, zoomable, with drawdown overlay)
- KPI strip: return, Sharpe, max DD, Calmar, win rate, trade count
- Position table: current holdings with unrealized PnL, mark-to-market price
- Trade timeline: every trade as a marker on the equity curve (click to expand: orderbook snapshot, fill details, audit trail)
- Risk metrics panel: rolling Sharpe, rolling drawdown, VaR (if enough history)
- Strategy explanation card: what strategy this agent is running, last backtest result
- **"Approve for live" button** (gated, see Phase 7)

**c) Leaderboard** — `/leaderboard`
- Table: rank, agent name, tier badge, equity, return %, Sharpe, max DD, Calmar, trade count
- Sort by any column
- Click any agent → agent detail page
- Season selector dropdown
- Highlight house baselines differently from external agents

**d) Backtest explorer** — `/backtest`
- Existing BacktestPage upgraded: strategy selector, market search, parameter inputs
- Results: equity curve, drawdown chart, trade PnL scatter, metrics table
- Walk-forward results: per-split equity curves overlaid + overfit score
- Monte Carlo: return distribution histogram + probability-of-ruin gauge
- Parameter heatmap: 2D color grid showing return by param combination
- "Use this strategy" button → pre-fills an order or starts paper trading with it

**e) Market browser** — `/markets`
- Search + filter markets by category, volume, liquidity
- Per-market page: price chart, orderbook depth visual, recent trades, signals
- "Run backtest on this market" quick action

**f) Approval dashboard (human-only)** — `/approvals`
- List of agents requesting live-tier promotion
- Per-request: agent's full paper track record, risk metrics, max drawdown, strategy description
- Approve / reject with signed confirmation
- Audit trail of all approval decisions

### 6.3 Charting library

Use **Recharts** (already React, lightweight, composable) for:
- Interactive equity curves with zoom + pan
- Drawdown area charts
- Trade PnL scatter plots
- Monte Carlo distribution histograms
- Parameter heatmaps
- Orderbook depth visualization

### 6.4 React router + layout

Replace the current single-page `<AgentArenaPage />` with a proper router:
- `react-router-dom` with sidebar navigation
- Persistent layout: sidebar (nav) + topbar (season selector, auth) + content area
- Dark mode toggle (agents trade at all hours)

### 6.5 Real-time updates

- WebSocket or SSE from the Flask API for equity curve ticks + new trade notifications
- Leaderboard auto-refreshes every 30s (already scaffolded)
- Agent detail page streams portfolio_snapshots in real-time

**Tests:** Cypress/Playwright smoke tests for critical paths (leaderboard loads, agent detail shows equity curve, backtest runs and displays results).

---

## Phase 7 — Human approval workflow + live tier

**Goal:** The bridge from paper to real money.

### 7.1 Promotion request flow

1. **Agent (or human) requests promotion.** `POST /api/v1/agents/:id/request-live` with a message explaining why.
2. **Platform generates a review package.** Automatically: paper track record summary (return, Sharpe, max DD, trade count, win rate), equity curve image, top 5 trades, worst 3 trades, strategy description, risk analysis.
3. **Human reviews on the approval dashboard** (`/approvals`). Can drill into any trade, see the audit trail, see the backtest that informed the strategy.
4. **Human approves with signed confirmation.** "I, [name], authorize agent [agent_name] to trade up to $[limit] of real money on Polymarket. I understand this involves real financial risk." Checkbox + confirmation code (2FA or email).
5. **Agent mode flips to `live`.** Season config carries `mode: paper|live`. RiskGate limits tighten for live (lower max_order_size, lower max_position_size).
6. **Kill switch.** Human can revoke live tier instantly via `/approvals` or `DELETE /api/v1/agents/:id/live`. All open orders cancelled, positions frozen.

### 7.2 Live execution bridge

- `LiveTrader` already exists at `src/polyclaw/trading/live_trader.py` (Phase 0 code)
- `TradingService` gains a tier-aware dispatch: `paper` tier → PaperTrader, `live` tier → LiveTrader
- Both go through the same RiskGate (premise P1)
- Every live trade is double-logged: `audit_log` + blockchain confirmation
- Live trades carry a `human_approved_at` field referencing the approval record

### 7.3 Safety layers

- **Daily loss limit.** If an agent loses more than X% in a day, auto-pause and notify human.
- **Drawdown circuit breaker.** If equity drops below starting_balance * (1 - max_dd_pct), freeze all positions.
- **Position concentration limit.** No single position > 20% of equity.
- **Cool-down after large loss.** If a single trade loses > 5% of equity, disable trading for 15 minutes.
- **Weekly human check-in.** If human hasn't viewed the agent dashboard in 7 days, auto-pause with notification.

### 7.4 Transparency + audit

- Every live trade links to the paper backtest that informed the strategy
- Human can see "this agent decided to buy X because [backtest showed Y return with Z Sharpe]"
- Full audit trail from research → backtest → paper trade → human approval → live trade
- Exportable trade log for tax reporting

**Tests:** promotion request flow, approval + signed confirmation, tier dispatch (paper vs live), kill switch cancels orders, daily loss limit auto-pause, drawdown circuit breaker.

---

## Phase ordering + dependencies

```
Phase 4: Season engine + composite leaderboard
  └─ no blockers (Phase 3 provides all infrastructure)
  └─ 1 week CC-time
  
Phase 5: Industry-grade backtesting
  └─ 5a (walk-forward) depends on Phase 4 seasons for data windows
  └─ 5b-5e are independent of each other
  └─ 2 weeks CC-time total (5a first, then 5b-5e in parallel)

Phase 6: Visualization + human-facing UI
  └─ depends on Phase 4 (season selector, composite metrics)
  └─ depends on Phase 5 (backtest result shapes: walk-forward, Monte Carlo)
  └─ 2-3 weeks CC-time (this is the big one, lots of frontend)
  
Phase 7: Human approval + live tier
  └─ depends on Phase 6 (approval dashboard UI)
  └─ depends on Phase 4 (season config for mode: live)
  └─ 1 week CC-time
```

**Critical path:** Phase 4 → Phase 5a → Phase 6 → Phase 7. Phases 5b-5e can run in parallel with Phase 6.

---

## Success criteria (V2)

**Phase 4:**
1. A 2-week season starts, runs, and finalizes without manual intervention.
2. Composite leaderboard shows Sharpe, max DD, Calmar for every agent.
3. Always-on sandbox season lets a dev register and trade any day.
4. 3+ house agents + 3+ external agents on the first real season leaderboard.

**Phase 5:**
5. Walk-forward analysis catches a known overfitting strategy that pure backtest misses.
6. Monte Carlo gives 90% confidence interval on strategy returns.
7. Parameter optimization finds a better momentum window than the default.
8. A custom-uploaded strategy runs in sandbox without escaping.

**Phase 6:**
9. A non-technical human can open the dashboard, find their agent, understand its performance, and decide whether to approve it — without reading any code or API docs.
10. Equity curves are interactive (zoom, hover, trade markers).
11. Agent detail page loads in under 2 seconds with 6 months of history.
12. Mobile-responsive (agents trade at all hours, humans check on phone).

**Phase 7:**
13. A human approves an agent for live trading via the UI with signed confirmation.
14. The approved agent executes a real trade through the live CLOB with the same RiskGate checks as paper.
15. A daily loss limit auto-pauses a live agent within 1 trade of the threshold.
16. Kill switch revokes live access and freezes positions within 5 seconds.

---

## NOT in scope (V2)

- Multi-venue support (Kalshi, Manifold, Drift)
- Custom model training / fine-tuning
- Social features (agent profiles, follows, comments, chat)
- Payouts / prize money for seasons
- Mobile native app (responsive web is enough for V2)
- Automated live trading without human approval (this is a safety boundary)

---

## Open questions (V2)

1. **Custom strategy sandboxing.** WebAssembly (Pyodide) vs subprocess with seccomp? Pyodide is more portable but can't access arbitrary Python packages. Subprocess is more flexible but harder to lock down. Leaning: subprocess with `--no-network` + tmpfs + resource limits for v1; Pyodide if we need browser-side execution later.

2. **Live trading wallet management.** Who holds the private key? Options: (a) platform custodies keys (simpler but trust-heavy), (b) user provides a signing proxy (safer but more DX friction), (c) smart contract with time-locked spending approval (strongest guarantees but complex). Leaning: (b) for v1 — the user sets up a dedicated wallet, grants the platform a spending allowance, and can revoke at any time.

3. **Real-time data.** Phase 5 backtests need higher-fidelity data than the current 60s `price_ticks`. Do we add a WebSocket ingester for sub-second ticks? Leaning: yes for Phase 5, but store separately (`price_ticks_live` at 1s resolution) to avoid bloating the 60s store.

4. **Frontend framework.** Current frontend is Vite + React + vanilla CSS. Phase 6 needs charting (Recharts), routing (react-router-dom), potentially a component library (Radix UI or shadcn/ui). Leaning: shadcn/ui + Tailwind for the Phase 6 rewrite — it's the fastest path to a polished look without custom CSS for every component.
