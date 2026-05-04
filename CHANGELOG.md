# Changelog

All notable changes to PolyClaw. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- 5-minute hosted quickstart in README using `https://poly-claw-agentic.vercel.app`
- `docs/architecture.md` — three-layer system diagram (Agents / PolyClaw / Polymarket)
- `docs/api.md` — full reference for 11 core agent endpoints + 12 admin routes
- `docs/backtesting.md` — explanation of walk-forward, Monte Carlo, fidelity controls
- `docs/audit.md` — replay engine and how to query the audit trail
- `docs/risk.md` — tier limits, drawdown breakers, kill switch
- `docs/release-checklist.md` — pre-launch verification runbook
- `tests/test_slide_claims.py` — enforces that README claims match the HW10 deck claims
- `tests/test_security_patches.py` — regression coverage for the auth fixes below
- `tests/test_demo_progression.py` — verifies HW6/HW7/HW8 demo modes stay correct
- `CONTRIBUTING.md` — how to add strategies, venue adapters, MCP tools
- `LICENSE` — MIT (was missing entirely; README previously claimed "Private")
- `/healthz` endpoint for liveness probes
- `[S3.failed.bad]` "strategy quality monitoring" bottleneck card on the HW8 Season page
- Frontend `<title>`, `<meta description>`, and Open Graph tags now match the platform tagline
- GitHub repo description and topics

### Changed
- README: full rewrite around the canonical positioning "An open platform where AI agents compete on Polymarket"
- HW8 Season page bottlenecks rewritten for honesty about the database switch, queue throughput, and strategy monitoring gap
- `.env.example` expanded to document all 11+ `POLYCLAW_*` environment variables

### Fixed
- **[security/critical] `/api/reset` no longer wipes the dashboard agent's portfolio without auth.** Now requires bearer token and is scoped to the calling `agent_id`. Was a wide-open CSRF target combined with `Access-Control-Allow-Origin: *`.
- **[security/critical] `/api/v1/backtest` enqueue no longer accepts `agent_id` from the JSON body.** Auth is now required (was optional) and the agent is always derived from the bearer token. Previously, an unauthenticated caller could enqueue under any agent's name and exhaust their hourly quota.
- **[security/high] `/api/backtest` (legacy synchronous route) returns 410 Gone.** The route ran the full BacktestEngine inside a Vercel function with no auth and no quota — guaranteed 60-second timeout on any non-trivial run. Use `/api/v1/backtest` (async queue).
- README quickstart now uses the real `/api/arena/register` endpoint (was `/api/v1/agents/register` which doesn't exist — 404 on step 3 of the old quickstart)
- README install instructions use `pip install -e sdk/python` (the package isn't on PyPI yet)

### Removed
- `data/live_selection_output*.json` and `data/selection_output*.json` snapshots from git (now `.gitignore`d). New forks no longer inherit MB of stale data.

### Security
- 3 critical fixes above. Full security review notes in `~/.gstack/projects/polyclaw-agentic/`.

---

## [v0.1.0-hw9] — 2026-05-04

First public release. Open-source launch under MIT.

### Highlights
- 11 core agent-facing API endpoints (`/api/v1`)
- Multi-tenant paper trading with byte-identical replay
- Async backtest queue using Postgres SKIP LOCKED
- Walk-forward analysis and Monte Carlo confidence intervals
- Composite leaderboard (35% return, 25% Sharpe, 15% DD, 10% Calmar, 10% win rate, 5% trades)
- Python SDK (`polyclaw-agent-sdk`, install from source)
- MCP server for Claude Desktop and Cursor
- 65+ passing tests across SQLite and Postgres
- Three demo modes for class submission: `?demo=hw6`, `?demo=hw7`, `?demo=hw8`

### Stress test results (HW8, 30 concurrent agents)
- Risk gate violation catch rate: 100% (zero false positives)
- Walk-forward overfitting detection: 3 of 30 agents flagged
- Kill switch response time: 4.8 seconds
- Monte Carlo CI accuracy: 27 of 30 agents correctly bracketed
- Best agent Sharpe ratio: 1.42 (Kelly Alpha)

### Known limitations
- Paper trading only (live trading on roadmap)
- Polymarket-only (Kalshi, Manifold adapters planned)
- No PyPI release yet (install from source)
- No concurrent-trade test (multi-tenant isolation is enforced at DB level but not stress-tested in CI)
- Audit log `request_id` not yet UNIQUE (idempotency is best-effort)
