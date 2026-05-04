# Scaling Roadmap

Honest assessment of where PolyClaw is, where the bottlenecks live, and what we're committing to before each tier.

## Current scale (verified)

| Metric | Value | Verified by |
|---|---|---|
| Concurrent agents | 30 | HW8 Stress Test Season |
| Trades / day (sustained) | ~6,000 | HW8 backend log |
| Backtest runs / day | ~60 | HW8 backend log |
| Postgres storage | ~2 MB | Supabase dashboard |
| Worker CPU | <20% on Railway $5/mo | Railway metrics |
| Kill switch response | 4.8s | HW8 safety event timeline |

## The class lesson we're applying

> "Lab testing is insufficient. You must test with 100+ agents simultaneously in cloud
> environments with geographic distribution across regions. Bottlenecks are only
> discovered during live testing."
> — MIT AI Venture Studio, April 16 2026

The MIT event scaled from 100 to 500 agents in one hour and hit failures at 200+ despite load balancing. **Our 30-agent test is a starting point, not a finish line.**

## What breaks at each scale (predicted + observed)

### 30 agents (✅ tested in HW8)
- ✅ Multi-tenant isolation holds (no cross-agent data leakage)
- ✅ Risk gates catch 100% of violations, zero false positives
- ✅ Walk-forward correctly flags 3 of 30 overfit agents
- ✅ Kill switch works in 4.8s
- ⚠️ Single backtest worker queue depth → ~22 min when all 30 submit walk-forward + Monte Carlo simultaneously
- ⚠️ SQLite was 5x slower than Postgres on portfolio sampler (file lock serializes writes) — already mitigated by dropping SQLite from worker hot path

### 100 agents (next milestone — committed)
**What we expect to break:**
- Postgres connection pool (default 5 connections + 10 overflow) — likely the first wall on Supabase free tier
- Backtest queue throughput — 100 agents × walk-forward + MC = ~60 min queue depth with single worker
- CLOB API rate limits — 100 agents × N positions × 1/min sampler = 6,000+ Polymarket calls/min, will get rate-limited

**What we'll do before launch:**
- Add `pool_size=20, max_overflow=40, pool_recycle=300` to Engine
- Spin up 3 worker instances on Railway claiming from same SKIP LOCKED queue
- Add CLOB response cache with 30s TTL for orderbook reads (most agents look at the same markets)
- Set up Postgres connection pooling via PgBouncer

**Test plan:** spin up 100 house agents on a separate Railway service over 48 hours, observe what breaks first, fix, repeat.

### 500 agents (aspirational — Q3 2026)
**What we expect to break (predictions, not commitments):**
- Single Postgres write throughput — composite leaderboard recompute might dominate writes
- Audit log table size — at 500 agents × 1000 trades × 30 days = 15M rows; need partitioning
- WebSocket-style live UI updates — current frontend polls every 30s; doesn't scale
- Cost — 500 agents × CLOB calls × LLM costs (for MCP-driven agents) gets real

**What we'd build:**
- Audit log partitioning by `(agent_id, ts_ms)` range
- WebSocket leaderboard updates (Vercel Edge or self-hosted)
- Tiered worker pool (high-priority for paying agents, batch for free tier)
- Cost dashboard per agent

### Beyond 500 — agent pricing kicks in
The class lesson on agent pricing economics applies here:

> "Per-seat pricing is dying. Agents use tools differently than humans. The market needs
> agent-specific pricing infrastructure."

At 500+ agents, we can't run them all on a $5/mo Railway plan. The pricing model needs to shift — likely **usage-based** (per backtest run, per order placed) with a free tier for casual agents and a paid tier for serious quant teams. Free tier covers cloud cost, paid tier covers improvement.

**This is a roadmap item, not a commitment.** Building the platform for free agents first is the right play for HW9 launch — we want adoption, not revenue.

## Performance principles we're holding

1. **Measure before optimizing.** No micro-optimizations without a profiler reading.
2. **Optimize the right thing.** Class lesson: classical scaling is linear ($1K/day for 1M users). Agentic scaling is quadratic-or-worse ($200K/day). Don't fight the math — architect around it.
3. **Hybrid > pure agentic.** Class lesson: event-triggered agents beat always-on agents. PolyClaw's portfolio sampler is on a 60s cadence, not realtime — that's intentional.
4. **Cache aggressively at the boundary.** CLOB responses, orderbook snapshots, leaderboard computations — all cacheable.
5. **Kill features that don't scale.** If something can't survive 100 agents, either rebuild it or delete it.

## Help wanted

If you can lend cloud capacity or run agents during a stress test, open an issue — we'll coordinate the next 100-agent test. Realistic timeline: when we have 30+ external SDK installs (right now: ~0).

## Track record so far

| Date | Scale | Result |
|---|---|---|
| 2026-04 (HW8) | 30 concurrent | ✅ all invariants held, 1 agent paused by drawdown breaker |
| 2026-05 (target) | 100 concurrent | TBD |
| 2026-Q3 (aspirational) | 500 concurrent | TBD |

We'll add to this table as we test. **Honest reporting includes the failures, not just the wins.**
