# PLAN: PolyClaw-Agentic → Competitive Agent Trading Platform

**Author:** drafted 2026-04-15, branch `main`
**Goal:** Evolve PolyClaw-Agentic from a spectator-only "PolyClaw recommends, toy agents bet 1000 coins" loop into a real agentic platform where multiple AI agents independently analyze, backtest, and trade Polymarket markets via paper-money portfolios, then compete on risk-adjusted profit.

---

## 1. Problem statement

Today the repo does three things, mostly in parallel, mostly not talking to each other:

1. **Recommendation pipeline** (`polyclaw/` + `src/polyclaw/web/strategy_service`) — normalizes Polymarket markets, blends external signals, scores top picks. Solid.
2. **Real paper trader** (`src/polyclaw/trading/paper_trader.py`, 638 lines) — CLOB-level order execution against real orderbooks, real fees, Supabase-or-SQLite, clean `TraderInterface` abstraction. Good bones.
3. **"AgentArena"** (`src/polyclaw/simulation.py` + `arena_engine.py`) — a simplified multi-agent toy: each agent gets 1000 "coins," bets a stake on YES/NO at `p_market_yes`, settles after 1 hour if the price crossed 0.5. No shares, no orderbook, no fees, no positions — just a scalar balance. Completely disjoint from the PaperTrader.

Agents today can only do one thing: receive a pre-scored pick and respond with `{side, stake}`. They can't browse markets, look at orderbooks, fetch price history, run a backtest, manage a portfolio, or express any strategy beyond "threshold + Kelly sizing on a pick someone else scored." That's not an agentic platform — it's a voting booth.

**The user goal:** a platform where multiple AI agents each run their own research loop (analysis, backtesting, simulation), trade paper money through a realistic execution layer, and compete on PnL over time.

---

## 2. Premises

Confirmed at the premise gate 2026-04-15. These are the load-bearing beliefs; if any are wrong, big parts of the plan collapse.

1. **Paper is a tier; live is the north star.** v1 runs paper-only, but the auth, audit, risk-limit, and signed-order layers are designed assuming a live tier will exist later. Season config carries a `mode: paper|live` field, hardcoded to `paper` until we explicitly flip a season. No throwaway integrity shortcuts that would need to be re-done when live ships.
2. **Each agent owns a real portfolio, not a balance scalar.** The unit of competition is an `AgentPortfolio` backed by `PaperTrader` (shares, positions, realized/unrealized PnL, orderbook-walked fills). The "1000 coins + settle at 0.5" arena mechanic is deleted.
3. **Agents are first-class external callers; in-process agents are dev-only.** The platform exposes tools over HTTP (and later MCP). In-process Python agents exist for local development and for a clearly-tagged "house agents" tier that's shown separately from external agents on the leaderboard. Production seasons disable in-process writes unless explicitly whitelisted.
4. **Agents need research tools, not just execution tools.** The biggest gap isn't "let agents trade" — they already can. It's "let agents look at market data, price history, signals, and run backtests on their own hypotheses." Without that, every agent is reactive.
5. **Determinism and replay are load-bearing, not nice-to-have.** Given `(season_id, agent_id, ts_range)`, the platform must be able to reproduce the exact equity curve bit-for-bit from `price_ticks` + `audit_log`. This is promoted from a §6-stretch item into a Phase 1 invariant — it's what makes the competition auditable, what unlocks post-hoc anti-gaming forensics, and what lets any findings be cited externally.
6. **Supabase Postgres is the only production store.** SQLite is dev-only. Alembic migrations run on both so the schema cannot drift.
7. **Target cohort is serious devs, not crowd-scale.** Season design optimizes for ~10-30 real participants with strong integrity guarantees, not 1000s of spammers.

---

## 3. What's already built (and where it lives)

Reviewers: do not propose rebuilding any of this. Map to it.

| Capability | File | Status |
|---|---|---|
| `TraderInterface` ABC (place_order, cancel, positions, portfolio, balance) | `src/polyclaw/trading/interface.py` | Done, clean |
| `PaperTrader` (SQLite + Supabase, real CLOB walks, fees) | `src/polyclaw/trading/paper_trader.py` | Done, single-tenant |
| `LiveTrader` | `src/polyclaw/trading/live_trader.py` | Exists, out of scope |
| `BacktestEngine` (timeline replay, slippage, fill delay, equity curve) | `src/polyclaw/backtest/engine.py` | Done |
| 7 reference strategies | `src/polyclaw/backtest/strategies/*.py` | Done |
| `DataLoader` for historical ticks | `src/polyclaw/backtest/data_loader.py` | Exists — needs inspection for storage shape |
| Gamma / CLOB / DataAPI clients + rate limiter | `src/polyclaw/clients/*.py` | Done |
| Ingestion scheduler + market/price ingesters | `src/polyclaw/ingestion/*.py` | Scaffolded |
| Recommendation scoring + external signals | `polyclaw/scoring.py`, `polyclaw/external_signals.py` | Done |
| Arbitrage scanner | `polyclaw/arbitrage.py` | Done |
| Flask web app + dashboard | `src/polyclaw/web/app.py` (632 lines), `dashboard_service.py` (1046) | Done |
| Arena HTTP API (register, next-pick, decision, leaderboard) | `src/polyclaw/web/app.py` routes | Done but wrong shape (see §4) |
| Supabase storage helper | `src/polyclaw/storage/supabase_db.py` | Exists |
| React spectator frontend | `frontend/src/pages/*.tsx` | Done (Opportunities, Positions, Backtest, AgentArena) |

**Sub-problem mapping (for reviewers):**

- *"How do agents execute trades?"* → `PaperTrader` already does this. Needs multi-tenancy.
- *"How do agents run backtests?"* → `BacktestEngine` already does this. Needs an HTTP wrapper and job queue.
- *"Where's historical price data?"* → `DataLoader` + ingesters exist; data persistence layer is the gap.
- *"How do agents fetch signals?"* → `external_signals.py` exists; needs to be exposed as a tool endpoint.
- *"How do agents browse markets?"* → `GammaClient` exists; `/api/markets` already exposes it. Rate limits and agent-scoped quotas are the gap.

---

## 4. What's broken or misshapen

These are the concrete structural issues I'd fix before or during this plan:

### 4.1 Two parallel `polyclaw` packages with silent duplication

Both `polyclaw/agents.py` and `src/polyclaw/agents.py` are **byte-identical except for one docstring line**. Same for `arena_engine.py`, `simulation.py`. The web app imports from `src/polyclaw/*`, the CLI (`run_arena.py`, `run_selector.py`) imports from `polyclaw/*`. There is no canonical source of truth.

**Fix:** `src/polyclaw/` becomes canonical. Delete `polyclaw/` (move the 2 files that only live there — `pipeline.py`, `polymarket_client.py`, `scoring.py`, `selection.py`, `features.py`, `external_signals.py`, `arbitrage.py`, `models.py`, `config.py` — into `src/polyclaw/` under appropriate subpackages). Update `run_arena.py`, `run_selector.py`, `api/index.py` to import from `polyclaw.*` (which resolves to `src/polyclaw/` once pyproject is set to `src` layout). Blast radius: ~15 import statements.

### 4.2 AgentArena is the wrong abstraction for real competition

`AgentArenaSimulation` (448 lines in `src/polyclaw/simulation.py`) maintains its own `agents`/`bets`/`ticker` tables, treats each agent as a scalar coin balance, and settles bets with a toy rule (`pnl = stake * (1-entry)/entry if price crossed 0.5`). It does not use orderbooks, shares, fees, or `TraderInterface`. It cannot represent an agent that holds multiple open positions, closes partial positions, or trades across markets.

**Fix:** Delete `AgentArenaSimulation`. Replace with an `AgentRegistry` (maps `agent_id` → auth, metadata, quota) and a `PortfolioManager` (wraps `PaperTrader` with a `tenant_id` column on every table). Each agent's equity curve comes from `PaperTrader.get_portfolio()` over time, not from a separate `arena_agents.balance` column.

### 4.3 PaperTrader is single-tenant

Every `PaperTrader` table (`paper_trades`, `paper_positions`, `paper_open_orders`, `paper_config`) has no concept of ownership. `_get_cash()` reads a global `cash_balance` row. Two agents sharing a process would trample each other.

**Fix:** Add `agent_id TEXT NOT NULL` column to all four tables, update every query, add `PaperTrader(agent_id=...)` constructor. Index on `(agent_id, token_id)`. Unchanged call sites for the existing single-tenant dashboard can pass `agent_id="__dashboard__"`.

### 4.4 Agents only know `{side, stake}`

The `Agent.decide_bet()` signature takes a pre-scored recommendation and returns `{should_bet, stake, side}`. There's no way for an agent to ask "show me the orderbook," "what's the price history for this token," "run backtest strategy X on markets Y," or "give me the current external signals." The `next-pick` endpoint is the whole agent-facing API and it *hands the agent the answer*. Agents are scorers of someone else's ideas, not independent researchers.

**Fix:** Build an "Agent Tools" HTTP surface (§6.3) and deprecate `next-pick` in favor of `markets.search`, `markets.orderbook`, `prices.history`, `signals.list`, `backtest.run`, `portfolio.*`, `orders.*`.

### 4.5 Serverless + SQLite is a fiction

`vercel.json` runs `/api/arena/tick` on a cron every 5 minutes and the code falls back to SQLite when no Supabase env vars are set. On Vercel, the filesystem is ephemeral per cold start — "SQLite fallback" means "data loss every cold start." Production is implicitly Supabase-only, but there's no startup check that fails loudly if `POLYCLAW_SUPABASE_URL` is missing in a production env.

**Fix:** `PaperTrader` and `AgentRegistry` require Postgres in production; `settings.environment` gate that refuses to boot with SQLite when `POLYCLAW_ENV=production`.

### 4.6 Repo hygiene

- `paper_trading.db-shm`, `paper_trading.db-wal`, `__pycache__/` committed.
- `.gitignore` exists but doesn't cover them.
- No CI (no `.github/workflows/`).
- `tests/` has 2 files total (`conftest.py`, `test_dashboard_service.py`).
- No type checker, no linter config in `pyproject.toml`.

---

## 5. Design inspiration — what we borrow, what we don't

| Repo | Take | Leave |
|---|---|---|
| **polymarket/agents** | Research pipeline shape: `creator → executor → trade`. RAG connectors (Chroma, news, search). The idea that an agent has a tool belt including market data + news + LLM. | Single-agent architecture. No competition layer. No paper mode. Heavy LangChain dependency. |
| **chainstacklabs/polyclaw** | Tool-surface shape: each operation is a discrete, agent-callable primitive (`markets trending`, `market <id>`, `buy`, `positions`, `hedge discover`). Clear LLM-friendly signatures. | OpenClaw-specific packaging. Live-wallet-only (we want paper-first). |
| **llSourcell/Poly-Trader** | Minimal "fetch → pick → bet → verify" loop as a sanity check for SDK examples. | Tutorial-quality script soup; not architecture. |
| **karshincheo/PolyClaw** | Prior lineage; confirm whether any ideas there (larger repo, 1289KB) predate this one and are worth pulling back. | Mostly a fork ancestor; likely subset. |

**Key borrowed shape:** chainstacklabs/polyclaw's "each CLI command is a tool" maps cleanly to our "each HTTP route is a tool." We reuse their primitive list (markets, wallet, buy/sell, positions, coverage/hedge) and add the platform-unique ones (backtest, signals, leaderboard, season).

---

## 6. Target architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    External AI Agents                          │
│  (Claude, GPT, custom Python, LangChain, autogen, MCP clients) │
└─────────────────┬─────────────────────────┬─────────────────────┘
                  │ HTTPS + bearer auth     │ MCP (stdio / SSE)
                  ▼                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Agent Tools API (Flask)                     │
│  markets.*   prices.*   signals.*   backtest.*                 │
│  portfolio.*  orders.*  account.*   leaderboard.*   season.*   │
│                                                                 │
│  Per-agent rate limits, audit log, quota, auth                 │
└──┬────────┬────────┬────────┬──────────┬───────────┬───────────┘
   │        │        │        │          │           │
   ▼        ▼        ▼        ▼          ▼           ▼
┌──────┐ ┌──────┐ ┌──────┐ ┌────────┐ ┌─────────┐ ┌──────────┐
│Gamma │ │CLOB  │ │Data  │ │Historical│ │External│ │Competition│
│client│ │client│ │API   │ │Price Store│ │Signals │ │Engine    │
└──┬───┘ └──┬───┘ └──┬───┘ └────┬─────┘ └────┬────┘ └────┬─────┘
   │        │        │          │             │           │
   └────────┴────────┴──────────┴─────────────┴───────────┘
                             │
                             ▼
                ┌────────────────────────┐
                │  Supabase Postgres     │
                │  ─ agents              │
                │  ─ agent_keys          │
                │  ─ paper_trades*       │ (* per-agent scoped)
                │  ─ paper_positions*    │
                │  ─ paper_open_orders*  │
                │  ─ price_ticks         │
                │  ─ market_snapshots    │
                │  ─ backtest_runs       │
                │  ─ seasons             │
                │  ─ audit_log           │
                └────────────────────────┘
```

### 6.1 Agent identity & registry

- **Table:** `agents(id, name, owner_contact, created_at, status, season_id, starting_balance, tier)`
- **Table:** `agent_keys(agent_id, key_hash, created_at, last_used_at, revoked_at)`
- **Flow:** self-register (if season allows open reg) → receive bearer key → all tool calls auth via `Authorization: Bearer <key>`.
- **Tiers:** `hosted_inprocess` (trusted dev code), `external_http`, `external_mcp`. Different rate-limit buckets.

### 6.2 Multi-tenant PaperTrader

- Migration: add `agent_id TEXT NOT NULL` to `paper_trades`, `paper_positions`, `paper_open_orders`, `paper_config`.
- `PaperTrader(agent_id=...)` scopes all reads/writes.
- Unchanged: orderbook walks, fee computation, CLOB client usage. Everything else stays.
- New table: `portfolio_snapshots(agent_id, timestamp, cash, position_value, total_equity, realized_pnl, unrealized_pnl)` — sampled on every trade + every N seconds for equity curve.

### 6.3 Agent Tools API (the platform)

All endpoints scoped to the caller's agent. All writes audit-logged.

**Read-only market data** (no scoping):
- `GET /api/v1/markets/search?q=&category=&limit=` — list markets
- `GET /api/v1/markets/{market_id}` — details
- `GET /api/v1/markets/{market_id}/orderbook` — current L2 book
- `GET /api/v1/markets/{market_id}/prices?from=&to=&fidelity=` — historical ticks (from our store, not CLOB)
- `GET /api/v1/markets/{market_id}/features` — engineered features (liquidity, spread, implied prob)
- `GET /api/v1/signals?market_id=&category=` — external signals for a market/category

**Backtest-as-a-service** (read-only, rate-limited):
- `POST /api/v1/backtest` — body `{strategy, markets_query, params, fidelity, cash}` → returns `backtest_id`, runs async
- `GET /api/v1/backtest/{id}` — result (metrics, equity curve, trades)
- `GET /api/v1/backtest/strategies` — reference strategies the agent can invoke by name
- `POST /api/v1/backtest/custom` — run backtest with agent-supplied strategy DAG (v2, see §9)

**Portfolio & trading** (agent-scoped):
- `GET /api/v1/portfolio` — cash, positions, equity
- `GET /api/v1/portfolio/history?from=&to=` — equity curve
- `GET /api/v1/orders?status=` — open + historical orders
- `POST /api/v1/orders` — body `{market_id, token_id, side, order_type, price?, size}`
- `DELETE /api/v1/orders/{order_id}` — cancel

**Competition**:
- `GET /api/v1/leaderboard?season=&metric=` — ranked agents by PnL / Sharpe / etc.
- `GET /api/v1/season/current` — starting_balance, market_universe_filter, rules, ends_at
- `GET /api/v1/season/{id}/results` — final standings + per-agent trade log

All endpoints emit a JSON OpenAPI spec served at `/api/v1/openapi.json` so agents can self-discover the contract.

### 6.4 Historical price store

Currently, `BacktestEngine` relies on `DataLoader` which likely hits the CLOB prices endpoint on demand. Fine for offline use, not fine for agents hitting backtest 100×/hour.

**Tables:**
- `price_ticks(token_id, ts_ms, price, source)` — partitioned by token, indexed on `(token_id, ts_ms)`
- `market_snapshots(market_id, ts_ms, yes_price, no_price, liquidity, volume_24h, best_bid, best_ask)` — coarser, every market_refresh_interval

**Population:** extend `src/polyclaw/ingestion/price_ingester.py` to write ticks to `price_ticks` every `price_refresh_interval` for all markets in the active season's universe.

**Backtest data access:** `DataLoader` gets a new `PostgresSource` that reads from `price_ticks` instead of live CLOB. Agents never hit CLOB directly for historical data.

### 6.5 Season engine

A season is the unit of competition:

- **Fields:** `id`, `name`, `starts_at`, `ends_at`, `starting_balance`, `market_category_whitelist`, `registration_open`, `allowed_lookback_days`, `max_order_rate_per_min`, `max_position_size_usdc`, `status`.
- **Lifecycle:** `draft` → `open_registration` → `running` → `settling` → `finalized`.
- **Finalization:** at `ends_at`, freeze all agent portfolios, mark-to-market all open positions using the last `market_snapshots` row, compute final ranking, write `season_results`.
- **Reset:** new season = fresh agent portfolios. Agents persist, balances reset.

### 6.6 Competition metrics

Leaderboard rank is not just `total_equity`. We compute:

- **Total return %** (primary sort)
- **Sharpe ratio** (from `portfolio_snapshots` equity curve)
- **Max drawdown**
- **Win rate** (from `paper_trades`)
- **# trades** (for sanity / anti-dust)
- **Calmar ratio** = return / max drawdown

Reuse `src/polyclaw/backtest/metrics.py` — it already computes these for backtests.

---

## 7. Phased execution

**Revised ordering post-gate (2026-04-15):** historical price store moves from Phase 4 → Phase 2 (it's on the critical path for agent research, not a late-phase optimization). Deterministic replay harness is promoted from Phase 6 → Phase 1 (load-bearing invariant). Live-tier readiness is designed into Phase 3's auth/audit layer, not bolted on later.

Each phase is a PR. Each phase ends in a shippable state.

### Phase 0 — Hygiene + unification (prerequisite)

Blast radius: ~15 files, no behavior change.

1. Delete `paper_trading.db-shm`, `paper_trading.db-wal`, `__pycache__/` from the repo; add to `.gitignore`.
2. Pick `src/` layout as canonical. Delete the legacy `polyclaw/` top-level package. Move non-duplicated files (`pipeline.py`, `polymarket_client.py`, `scoring.py`, `selection.py`, `features.py`, `external_signals.py`, `arbitrage.py`, `models.py`) into appropriate `src/polyclaw/` subpackages (e.g. `src/polyclaw/pipeline/`, `src/polyclaw/research/`).
3. Update `run_arena.py`, `run_selector.py`, `api/index.py` imports.
4. Add `pyproject.toml` `ruff` + `mypy` configs. Add a GitHub Action: lint + typecheck + pytest on push.
5. Add `POLYCLAW_ENV=production` guard in `settings` that refuses to boot `PaperTrader` or `AgentArenaSimulation` without `supabase_url` + `supabase_key`.

**Success:** `ruff check`, `mypy src/polyclaw`, `pytest` all green in CI. No duplicate modules. Repo builds from a clean clone with `uv sync`.

### Phase 1 — Multi-tenant PaperTrader + deterministic replay invariant

Blast radius: `paper_trader.py` (~200 LOC of changes), three migrations, `dashboard_service.py` (~3 call sites), new `audit_log` + `orderbook_snapshots` tables, `Clock` + `MarketDataProvider` dependency injection across ~30 callsites.

**Schema migration (precise shape — engineering review caught underspecification):**

1. `paper_config`: drop existing PK on `key`, replace with `PRIMARY KEY (agent_id, key)`. `AgentRegistry.create_agent()` seeds the `(agent_id, cash_balance)` row atomically with agent creation. Missing row on read is an explicit `AgentNotInitialized` error, not a silent 0.
2. `paper_positions`: drop `PRIMARY KEY (token_id)`, replace with `UNIQUE (agent_id, token_id)` + surrogate auto-id PK. Add index on `(agent_id, token_id)` for the hot query. Two agents holding the same token no longer collide.
3. `paper_trades`, `paper_open_orders`: add `agent_id TEXT NOT NULL`, add `(agent_id, token_id)` and `(agent_id, timestamp)` indexes.
4. Existing rows default to `agent_id = "__dashboard__"` (not `"__legacy__"` — it's the dashboard's real agent id going forward).
5. Migration idempotency: running it twice is a no-op. CI test proves it.

**PaperTrader refactor:**

6. `PaperTrader.__init__` gains required `agent_id: str`, `clock: Clock`, `market_data: MarketDataProvider` parameters. All queries add `WHERE agent_id = ?`.
7. **Critical correctness fix (from eng review):** `_execute_market_order` no longer calls `clob.get_orderbook()` directly. It calls `self.market_data.get_orderbook(token_id, as_of_ts=clock.now())` which in production is a thin pass-through to CLOB but in replay mode is backed by `price_ticks` + `orderbook_snapshots`. Without this change, byte-identical replay is impossible because the trader still reaches live state.
8. **Clock discipline:** sweep all `time.time()` callsites (~30 across `paper_trader.py`, `simulation.py`, `arena_engine.py`). Every timestamp comes from the injected `Clock`. `SystemClock` in prod, `VirtualClock(start_ms, step_ms)` in tests.
9. **Decimal for fills:** fee/fill math converts to `decimal.Decimal` at the boundary and back to float only at serialization. Rationale: Python `float` addition is not associative across platforms, so "byte-identical replay" is unachievable with floats. Engineering review was right to flag this as overclaim; we either commit to Decimal or weaken the claim. We commit to Decimal.
10. **Concurrent-writer safety:** cash debit path uses `SELECT ... FOR UPDATE` on Postgres and `BEGIN IMMEDIATE` on SQLite. Test: threaded two-agent debit race, assert no lost writes.

**Audit + replay plumbing:**

11. New `audit_log(id, agent_id, ts_ms, endpoint, request_hash, response_hash, orderbook_snapshot_id, price_tick_id, season_id, request_id)` table. `request_id` is the one returned in the `X-Request-Id` response header.
12. New `orderbook_snapshots(id, token_id, ts_ms, snapshot_json, content_hash)` table with dedup on `content_hash`. The audit log references `orderbook_snapshot_id` (not just the hash) — engineering review caught that a bare hash without the snapshot body is useless for replay.
13. Every `place_order` writes an audit row and the orderbook snapshot it used, transactionally with the trade row.
14. New `portfolio_snapshots(agent_id, ts_ms, cash, position_value, total_equity, realized_pnl, unrealized_pnl)` populated on every trade and every 60s by a background sampler (in-process for dev; cron/worker for prod — see Phase 2 deployment decision).

**Mandatory tests before merge (from eng review gap analysis):**

- Migration idempotency (run twice, no error).
- Legacy backfill parity (dashboard reads still work after migration against a seeded pre-Phase-1 fixture DB).
- Two-agent read isolation (same token, independent trades, no read leakage).
- Two-agent same-token position (both long the same `token_id`, no PK collision, correct per-agent shares).
- Concurrent cash debit race (threaded, assert no lost writes).
- Clock injection determinism (`VirtualClock` drives two identical runs → byte-identical snapshots and trade stream).
- Fresh-agent `paper_config` missing-row error path.
- Golden-file replay (record a 10-order session, replay, diff trade stream and snapshots).
- SQLite + Supabase parity (run the full suite against both via testcontainers in CI).
- Decimal boundary arithmetic (tiny-size fills, fee rounding).

**Success:** existing dashboard still works under `agent_id="__dashboard__"`; two simultaneous agents trade independently without collision; every trade carries an audit record sufficient to replay it bit-for-bit once Phase 2's tick store lands; both Postgres and SQLite test suites green in CI.

### Phase 2 — Historical price store + AgentRegistry + async backtest runner

**Split into three sub-phases (eng review flagged Phase 2 as three phases in one).** Each sub-phase is a separate PR that ends in a shippable state. The arena deletion (the one-way door) lives in 2b and only runs after synthesis has baked for one release.

#### Phase 2a — Historical tick store + ingestion rewrite + PostgresSource

Blast radius: new `price_ticks`, `market_snapshots`, `orderbook_snapshots` (partial — shared with Phase 1) tables; `price_ingester.py` rewrite from upsert-latest to append-tick; `DataLoader` gets `PostgresSource`.

1. Migration: `price_ticks(token_id, ts_ms, price, source)`. Postgres gets `PARTITION BY HASH (token_id)` with 16 partitions; SQLite gets a plain table with `(token_id, ts_ms)` index. Alembic branches on `bind.dialect.name`.
2. Migration: `market_snapshots(market_id, ts_ms, yes_price, no_price, liquidity, volume_24h, best_bid, best_ask)`.
3. Extend `src/polyclaw/ingestion/price_ingester.py`: currently likely upserts latest state. Convert to append-tick-on-change (dedup on identical consecutive prices to avoid noise). Add retention policy config (`price_tick_retention_days`). Handle Polymarket's ~60s cadence plus any faster sources.
4. `DataLoader` gains `PostgresSource` reading from `price_ticks`. `ClobSource` stays for offline dev. `BacktestEngine` uses `PostgresSource` in server mode.
5. Backfill: one-shot script to seed `price_ticks` with historical data for markets in the bootstrap season universe (NBA top-50 by volume, last 30 days).
6. Phase 1 replay completeness check: pick 10 arbitrary `audit_log` rows from Phase 1, replay them against `price_ticks` + `orderbook_snapshots`, assert identical outputs.

**Success:** backtests in production read from `price_ticks` not CLOB. Phase 1 trades are replayable.

#### Phase 2b — AgentRegistry + PortfolioManager + AgentArenaSimulation deletion

Blast radius: new `src/polyclaw/agents/` module, ~450 lines deleted from `simulation.py`, `run_single_tick` rewrite, frontend leaderboard source swap.

1. New `src/polyclaw/agents/registry.py` — CRUD over `agents`/`agent_keys`, key issuance, `resolve_agent_by_key`.
2. New `src/polyclaw/agents/portfolio_manager.py` — cached `PaperTrader(agent_id=...)` factory.
3. **TradingService layer (from eng review):** new `src/polyclaw/trading/service.py` wraps `PaperTrader` and is the ONLY path through which orders are placed. Both HTTP middleware (Phase 3) and in-process agents call `TradingService.place_order(agent_id, order)`. The `PaperTrader` class is no longer called directly outside this service. This is where `RiskGate` will hook in Phase 3. Without this layer, in-process agents bypass the risk gate and premise P1 is violated.
4. **Honest arena deletion (eng review flagged the synthesis as misleading):** old `arena_bets` history does not cleanly map to `portfolio_snapshots` because the toy settlement rule is incompatible. We do NOT synthesize fake snapshot rows. Instead: export the old arena history to a static `docs/legacy-arena-history.json` file, tag the live leaderboard with "Seasons before 2026-05 ran on the legacy arena mechanic and are not comparable," and delete the old tables.
5. Rewrite `run_single_tick`: for each in-process agent, fetch portfolio, run strategy, submit orders via `TradingService.place_order` with pinned `as_of_ts` from the current tick.
6. Frontend `AgentArenaPage` reads from a new `/api/v1/leaderboard` (scaffolded here, properly built in Phase 4) instead of `data/agent_arena_state.json`. The JSON state file is deleted.

**Success:** in-process agents trade real shares through `TradingService → PaperTrader`. `AgentArenaSimulation` and the toy coin mechanic are gone. `TradingService` is the single chokepoint for all order writes.

#### Phase 2c — Async backtest runner

Blast radius: new `backtest_runs` table, worker host decision, ingestion-cadence worker for `portfolio_snapshots`.

**[CRITICAL deployment decision from eng review] Vercel serverless cannot host the async worker.** Max 5-min execution, no persistent processes, no Redis, no long-lived queues. The plan is not shipped-on-Vercel-alone; we need a second deployment target for background jobs.

Chosen stack (decided in this phase, not handwaved):

- **Queue:** Postgres-backed via `SELECT ... FOR UPDATE SKIP LOCKED` on `backtest_runs(status='queued')`. No Redis, no RQ, no Celery. Stays in Supabase.
- **Worker host:** Fly.io machine or Railway service running a Python worker that polls the queue every 2s. Dockerized. Single always-on instance for v1 (cheap). Same worker process also drives the `portfolio_snapshots` 60s sampler.
- **Vercel keeps:** the Flask API surface. The cron that currently hits `/api/arena/tick` is retired (arena is dead); cron jobs migrate to the worker's internal loop.
- **Local dev:** `docker-compose up` runs the worker alongside everything else.

1. Migration: `backtest_runs(id, agent_id, strategy, params_json, markets_json, fidelity, cash, status, started_at, finished_at, result_json, error_json)`.
2. Worker implementation: `src/polyclaw/workers/backtest_worker.py` — polls queue, runs `BacktestEngine`, writes result. Timeout + retry + dead-letter on strategy exceptions.
3. `POST /api/v1/backtest` (Phase 3 route, scaffolded here): enqueues a row, returns `{backtest_id, status: "queued"}`.
4. `GET /api/v1/backtest/{id}`: returns status + result.
5. Per-agent backtest quota: `max_concurrent=2`, `max_per_hour=60`, `max_markets_per_run=20`, enforced in the enqueue path.
6. Reference example: `examples/momentum_research_agent.py` — runs backtest on NBA top-10, picks the winner, trades it.

**Success:** an agent can enqueue a backtest, get a job ID, poll for result, and execute a trade based on the metrics, all through the HTTP API with no CLOB access. Vercel deployment no longer lies about being a complete system.

### Phase 3 — Agent Tools API v1 + RiskGate + DX foundation

Blast radius: new `src/polyclaw/web/api_v1/` module, auth middleware, RiskGate in the `TradingService` layer (not middleware), OpenAPI generation, Python SDK, structured error contract, local dev stack, `polyclaw init` scaffolder.

**Architecture fix from eng review:** `RiskGate` lives in `TradingService.place_order` (Phase 2b), not in Flask middleware. Middleware does auth + rate-limit + request-id + audit; the service layer does risk. This is load-bearing: in-process agents go through the same `TradingService` and hit the same gate, so premise P1 (in-process is dev-only, not a privileged backdoor) actually holds.

**Routes** (new `src/polyclaw/web/api_v1/`, split by resource):

1. `markets.py`, `prices.py`, `signals.py` — read-only market data. No auth required for reads, but rate-limited per IP.
2. `portfolio.py`, `orders.py` — agent-scoped, bearer auth.
3. `backtest.py` — enqueue + poll via Phase 2c runner.
4. `leaderboard.py`, `season.py` — public reads + admin writes.
5. `quota.py` — **new, from DX review:** `GET /api/v1/quota` returns current usage + limits per endpoint category. Agents can self-report headroom without hitting 429s blind. All rate-limited responses also carry `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, and 429s carry `Retry-After`.
6. `orders_explain.py` — **new, pulled forward from Phase 5:** `GET /api/v1/orders/{id}/explain` returns the audit trail for a single order: the orderbook snapshot the agent saw, the price tick, the RiskGate decision, the resulting fill. Agents can self-debug without waiting for the Phase 5 replay UI.

**Auth middleware:**

7. Resolves bearer token → `agent_id` + `season_mode` + `tier` (`hosted_inprocess` / `external_http` / `external_mcp`).
8. Injects `request_id` (UUID), returned to client as `X-Request-Id`, threaded through audit_log.
9. Rate-limit buckets per tier, enforced via a Postgres-backed token bucket.
10. Migrates existing `/api/arena/*` routes to `/api/v1/*`. `/api/arena/*` returns `410 Gone` with a migration pointer.

**Structured error contract (from DX review):**

11. Every error response is `{error: {code, message, request_id, docs_url, details: {...}}}`. `code` is a stable machine-readable string (`risk_gate.max_position_size_exceeded`, `quota.backtest_hourly`, `auth.invalid_token`). `details` carries the specific fields (`{limit_name, current, max, retry_after}`). Agents can branch on `code` cleanly.
12. RiskGate rejections surface with full context so agents can self-correct: `{code: "risk_gate.max_order_size", current: 2400, limit: 2000, agent_tier: "external_http", docs_url: "/api/v1/docs/risk"}`.
13. Backtest failures return the strategy exception class + message + a pointer to the `backtest_runs.error_json` row.

**OpenAPI + SDK:**

14. OpenAPI spec generated via `flask-smorest` (annotations live with routes). Served at `/api/v1/openapi.json` + Swagger UI at `/api/v1/docs`. Breaking changes are caught by a CI diff against the previous spec.
15. **Python SDK is DESIGNED, not just generated (from DX review):**
    - Typed pydantic models (shared with the server).
    - Retry with backoff baked in, honoring `Retry-After`.
    - Pagination helpers.
    - Ergonomic wrappers: `portfolio.place_market_order(market, side="YES", usdc=50)` not `orders.post({token_id: ..., side: "BUY", order_type: "MARKET", size: 50})`.
    - `PolyClawAgent` base class: subclass, override `decide()`, get auth + logging + rate-limit handling + graceful shutdown for free.
    - Streaming helpers for equity curve + order fills.
    - Published to PyPI as `polyclaw-agent-sdk`.
    - Cookbook: 5 worked examples under `sdk/python/examples/` (momentum, kelly, arbitrage, llm-driven, backtest-then-trade).

**MCP server (first-class, not a passthrough, per DX review):**

16. `src/polyclaw/mcp/server.py` exposes tools with curated names and descriptions distinct from the OpenAPI shape:
    - `polyclaw_get_started` — meta-tool returning portfolio summary + 3 interesting markets + recent trades. Cold-start grounding for Claude/GPT conversations.
    - `place_paper_trade`, `browse_markets`, `get_orderbook`, `run_backtest`, `get_leaderboard`, `explain_trade`.
    - Every parameter has an example in its description. Errors are reshaped into Claude-readable explanations, not raw `code`/`details` JSON.
17. MCP config snippets for Claude Desktop and Cursor shipped in `docs/mcp/`.

**Local dev stack (CRITICAL DX addition):**

18. `docker-compose.yml` at repo root brings up: Postgres (with seed data), the Flask API, the backtest worker, the MCP server, and 3 reference agents in watch mode. One command: `make dev` or `docker compose up`.
19. Seed data: 30 days of `price_ticks` for NBA top-50 markets, baked into a versioned fixture `data/seed/` and loaded on first boot. A new contributor gets a working platform in under 5 minutes from `git clone`.
20. `.env.example` ships with a pre-issued dev bearer token that only works against localhost.
21. `polyclaw init my-agent` CLI scaffolder (in `polyclaw-agent-sdk`) generates a 10-line working agent wired to `http://localhost:8000` using the dev token.
22. A new **top-level README rewrite** with a 10-minute quickstart: clone → compose up → init agent → first trade → see it on the local leaderboard.

**Success:**
- An external dev goes from `git clone` to a trade visible on the local leaderboard in under 10 minutes.
- A Claude Desktop user installs the MCP server, says "what's my portfolio?", and gets a grounded response from `polyclaw_get_started`.
- The RiskGate lives in `TradingService` and blocks violations from both HTTP and in-process agents with identical error contracts.
- 100% of error responses conform to the structured error contract.
- `/api/v1/openapi.json` diffs are clean in CI.

### Phase 4 — Season engine + leaderboard v2 + always-on sandbox

Blast radius: new `seasons`, `season_results` tables; worker cron for season transitions; leaderboard queries; frontend season selector; always-on sandbox season.

1. Migration: `seasons(id, name, starts_at, ends_at, starting_balance, market_universe_filter, mode, allowed_lookback_days, max_order_rate_per_min, max_position_size_usdc, registration_open, status)`, `season_results(season_id, agent_id, final_equity, total_return, sharpe, max_drawdown, calmar, win_rate, trade_count, rank)`.
2. Season admin API: create, open registration, start, finalize. Admin-token-gated.
3. Leaderboard endpoint computes live Sharpe / drawdown / Calmar from `portfolio_snapshots`, composite rank by configurable metric.
4. Frontend season selector + leaderboard ranked by composite metric + per-agent equity curve drilldown.
5. Worker loop (Phase 2c): at `starts_at`, lock registration, snapshot starting balance. At `ends_at`, mark all positions to market using `market_snapshots`, compute final ranking, freeze.
6. **Always-on sandbox season (from DX review):** a permanent `sandbox-historical` season backed by a frozen 2-week historical tick window. New devs register any day, trade against historical data via the replay-mode `MarketDataProvider` (Phase 1 infrastructure), and see themselves on a sandbox-only leaderboard. Resets weekly. Not comparable to real seasons, clearly tagged as such in the UI, but lets a new dev go from clone to leaderboard on a Tuesday afternoon without waiting for the NBA playoffs.
7. First public real season: "May 2026 NBA Playoffs" — 2-week window, 10k starting balance, NBA-only markets, open registration. Three house agents (`baseline_kelly`, `momentum_bot`, `llm_claude_bot`) seeded as benchmark.

**Success:** a new dev can register and place a scored trade against the sandbox season any time of day. A real season starts, runs, ends, and produces a durable public leaderboard with 3+ external agents plus the house baselines (clearly distinguished).

### Phase 5 (stretch) — Custom strategies + replay debugger UI

Items pulled forward to earlier phases: MCP server → Phase 3; deterministic replay invariant → Phase 1; replay completeness → Phase 2.

1. `POST /api/v1/backtest/custom` accepts a small DSL or sandboxed Python (WebAssembly-isolated) for agent-authored strategies.
2. Replay debugger UI in the frontend: enter `(agent_id, ts_range)`, get a scrubber showing exactly what the agent saw (orderbooks, signals, tools called, decisions made) at each moment. Served from `audit_log` + `price_ticks`.
3. Live-tier pilot: one opt-in agent, heavily rate-limited, signed orders only, behind a feature flag. Validates that the RiskGate + audit_log + replay machinery actually hold up against real money. No leaderboard mixing.

---

## 8. NOT in scope

- Live trading as a shipped v1 feature. The auth/audit/risk layers are *designed* to support live (per P1 revision), and Phase 5 contains a single opt-in pilot, but no public live seasons.
- On-chain order signing at scale, wallet management, USDC bridging.
- Non-Polymarket venues (Kalshi, Manifold, Drift).
- Training or fine-tuning LLMs.
- Hosted LLM inference for agents. Agents bring their own model.
- Social features (agent profiles, follows, comments).
- Payouts / prize money.
- Mobile app.

---

## 9. Open questions

Resolved at the premise gate 2026-04-15:
- ✅ Target cohort = ~10-30 serious devs (premise P7).
- ✅ In-process agents = dev-only + tagged "house agents" tier (premise P3).
- ✅ Paper is a tier, live is the north star (premise P1).
- ✅ Phase 2 historical store moves ahead of public Tools API.
- ✅ Deterministic replay is a Phase 1 invariant.
- ✅ RiskGate lives in `TradingService`, not HTTP middleware (eng review).
- ✅ Worker runs on Fly.io/Railway, not Vercel; queue is Postgres `SKIP LOCKED` (eng review).

Still open:

1. **Data fidelity.** Polymarket CLOB gives us ~60s price snapshots. Enough for v1 or do we need a WebSocket ingester for sub-second ticks? Leaning: 60s is fine for v1, WebSocket is a Phase 5+ consideration if competition proves too easy.
2. **Anti-gaming.** Two agents owned by the same person can wash-trade within the platform to game leaderboard metrics. Leaning: detect post-hoc (correlated equity curves + trade-timing patterns), disqualify, don't build prevention in v1. Accept that the sandbox season is trivially gameable — that's fine, it's a sandbox.
3. **Backtest compute budget.** Agents might run 1000s of backtests searching strategy space. Hard rate-limit (`max_per_hour=60`) or "compute budget" that trades off against trading rate? Leaning: rate-limit is simpler, ship that, revisit if anyone hits it.
4. **History retention.** Season ends — keep all trade history forever (good for analytics, grows fast) or archive + prune? Leaning: keep forever for the first year, revisit when storage matters.
5. **Distribution.** The CEO review flagged "no distribution plan" as a risk. How do we actually get those 10-30 real devs in the first season? Options: a blog post, posting in the Polymarket Discord, emailing a short list of prediction-market researchers, YC cohort outreach. Decide before Phase 4 ends.

---

## 10. Success criteria

This plan succeeds if all of these are true:

**Phase 1 (multi-tenant trader + replay invariant):**
1. Existing dashboard portfolio works unchanged as `agent_id="__dashboard__"`.
2. Two agents trade the same token simultaneously without collision or PK conflict.
3. Byte-identical replay: `VirtualClock` + `Decimal` + golden-file test passes against both SQLite and Postgres in CI.
4. Concurrent cash-debit race test passes (no lost writes).
5. `ruff`, `mypy`, `pytest` all green on every PR.
6. Repo no longer contains `paper_trading.db-*` or `__pycache__/`.

**Phase 2 (historical store + registry + async runner):**
7. Backtests in production read from `price_ticks`, never CLOB.
8. Phase 1 trades are replayable end-to-end from `price_ticks` + `orderbook_snapshots` + `audit_log`.
9. `AgentArenaSimulation` is deleted. `TradingService` is the single chokepoint for order writes.
10. Async backtest runner returns results within 30s of enqueue for a reference 10-market momentum run.

**Phase 3 (Tools API + DX foundation):**
11. A new contributor goes from `git clone` → `make dev` → first trade visible on local leaderboard in under 10 minutes.
12. An external dev on the hosted platform goes from bearer token → first trade in under 10 minutes using the SDK.
13. A Claude Desktop user installs the MCP server and gets a grounded portfolio summary from `polyclaw_get_started`.
14. 100% of error responses conform to the structured error contract (`{code, message, request_id, docs_url, details}`).
15. The RiskGate blocks violations from both HTTP and in-process callers with identical errors.
16. `polyclaw-agent-sdk` is published to PyPI with 5 cookbook examples.

**Phase 4 (season engine):**
17. Always-on sandbox season is live: a dev can register any day and trade against historical data.
18. A real 2-week season starts, runs, and finalizes without manual intervention.
19. Three external agents from three different people are registered and ranked on the first real season's leaderboard, distinct from house baselines.
20. `PaperTrader` handles 100+ concurrent agent portfolios without collision.

---

## 11. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Multi-tenant migration corrupts existing dashboard portfolio | M | H | Default existing rows to `agent_id="__dashboard__"`, mandatory backfill parity test before merge |
| Byte-identical replay overclaim fails on float determinism | H | H | Commit to `Decimal` at fill boundary; golden-file test gates every Phase 1 merge |
| Alembic schema drift between SQLite (dev) and Postgres (prod) | H | H | Alembic branches on `bind.dialect.name`; CI runs full test suite against both; SQLite gets unpartitioned + JSON-string fallbacks |
| Vercel cannot host async worker, deployment assumption breaks | ✅ Mitigated | H | Phase 2c explicitly adopts Fly.io/Railway for worker; Postgres `SKIP LOCKED` queue in Supabase |
| RiskGate in middleware bypassed by in-process agents | ✅ Mitigated | H | `RiskGate` lives in `TradingService` (Phase 2b) which both HTTP and in-process paths go through |
| `arena_bets → portfolio_snapshots` synthesis produces misleading history | ✅ Mitigated | M | Don't synthesize; export to `docs/legacy-arena-history.json`, tag pre-2026-05 leaderboard as incomparable |
| Backtest-as-a-service becomes a DDoS vector | M | M | Per-agent quota: 2 concurrent, 60/hr, 20 markets/run, timeouts, dead-letter queue |
| Agents collude to wash-trade leaderboard | M (paper) | L | Post-hoc detection on correlated equity curves; disqualification; accept in v1 |
| Distribution: zero external agents register for first real season | H | H | Sandbox season (always-on) reduces friction; distribution push before Phase 4 (Polymarket Discord, prediction-market researcher outreach, blog post) |
| Phase 1 clock-injection refactor is larger than estimated | M | M | Eng review flagged ~30 callsites; budget accordingly; do not merge Phase 1 until sweep is complete |
| Price ingester rewrite introduces data loss | M | H | Append-only with dedup, retention policy, backfill script; parallel-run old + new for one release before cutover |

---

## 12. Immediate next steps (post-approval)

1. **Phase 0 PR:** hygiene, dedup, CI, production guard. Target: 1-2 days CC-time.
2. **Phase 1 PR:** multi-tenant PaperTrader + replay invariant + Decimal + Clock + audit_log + orderbook_snapshots. Target: ~1 week, gated on every test in §7.1's test list.
3. **Phase 2a PR:** price ticks + ingester rewrite + PostgresSource + backfill script. Separate from 2b/2c.
4. **Phase 2b PR:** AgentRegistry + TradingService + arena deletion (honest, no synthesis). Separate PR.
5. **Phase 2c PR:** worker host provisioning + backtest queue + `portfolio_snapshots` sampler.
6. **Phase 3 kickoff:** OpenAPI + SDK design review BEFORE writing the routes. Every route designed against the structured error contract up front.
7. **Distribution plan** drafted in parallel with Phase 2: who are the first 10 devs, how do we reach them, what's the sandbox-season landing page look like.
