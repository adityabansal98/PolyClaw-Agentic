# Contributing to PolyClaw

PolyClaw is an active multi-year project. We want contributors. The bar is not "be an experienced open-source maintainer" — the bar is "have something that makes the platform better and isn't actively dangerous."

## Quick start for contributors

```bash
git clone https://github.com/adityabansal98/PolyClaw-Agentic.git
cd PolyClaw-Agentic
make dev              # docker compose up — Postgres + API + worker
make test             # full pytest suite
make lint             # ruff check + format
```

If `make dev` fails, see the Troubleshooting section in [README.md](README.md#troubleshooting).

## Good first issues

| Type | Where | Examples |
|------|-------|----------|
| **New built-in strategies** | `src/polyclaw/backtest/strategies/` | RSI mean-reversion, Bollinger bands, sentiment-weighted Kelly |
| **Venue adapters** | `src/polyclaw/clients/` | Kalshi, Manifold, Drift, Hyperliquid |
| **MCP tools** | `src/polyclaw/mcp/` | New tool exposures for Claude Desktop / Cursor |
| **Risk gate policies** | `src/polyclaw/risk/` | Daily drawdown, correlated-position limits, circuit breakers |
| **SDK improvements** | `sdk/python/` | Async client, better error types, retry logic |
| **Documentation** | `docs/` | Tutorials, custom-strategy guides, architecture explainers |
| **Frontend polish** | `frontend/src/` | Better charts, mobile responsiveness, dark/light theme toggle |

If you're not sure where to start, open a discussion or skim the [Roadmap section](README.md#whats-next-roadmap).

## How to contribute

1. **Open an issue first** for non-trivial changes. Saves both of us the "you built the wrong thing" conversation.
2. **Fork + branch.** Branch name like `feat/kalshi-adapter` or `fix/audit-log-idempotency`.
3. **Write tests.** New code paths need tests. New strategies need backtest results checked in (see `tests/test_strategies/`).
4. **Run the slide-claim verifier.** `pytest tests/test_slide_claims.py -v` — this enforces that the README and docs stay aligned with the platform's claimed capabilities. Don't break it; if your change requires updating a claim, update both code and slide registry.
5. **Lint.** `make lint` — ruff. CI will reject unformatted code.
6. **Open a PR** with: what changed, why, test plan, screenshots (for UI changes), API impact (for backend changes).

## Code style

- **Python:** Type hints on public functions. Docstrings on classes. f-strings everywhere. Decimal for money (never float).
- **TypeScript:** Functional components. No `any` unless documented why. Run `npm run build` before pushing — TS errors fail CI.
- **Commits:** Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`). One logical change per commit.

## What we will not merge

- New direct-Polymarket API calls outside `src/polyclaw/clients/` — everything goes through the client wrappers
- Order placement that bypasses `TradingService.place_order()` — single chokepoint is the entire point
- Synchronous backtests in HTTP routes — use the async queue (`/api/v1/backtest`)
- `Math.random()` in mock data — use seeded PRNGs for determinism (see `frontend/src/lib/demoData.ts`)
- Hardcoded `agent_id` from request body — auth-derived only (this was a real security hole — see CHANGELOG)
- Unscoped CORS on mutating routes
- Code without tests
- "It works on my machine" — test with `POLYCLAW_TEST_POSTGRES=1` and SQLite both

## Security disclosures

If you find a security issue, **do not open a public issue**. Email `security@polyclaw.dev` (placeholder) or DM the maintainer directly. We'll respond within 48 hours.

## Code of conduct

Be a good colleague. Don't be a jerk. Disagree with ideas, not people. We reserve the right to remove anyone who makes the project unwelcoming for others.

## Project ownership

PolyClaw is currently maintained by [@adityabansal98](https://github.com/adityabansal98). Major architectural decisions get a CEO review (see `~/.gstack/skills/plan-ceo-review`). PRs that touch trading correctness, audit invariants, or multi-tenant isolation get an extra review pass — these are the load-bearing parts.

## License

By contributing, you agree your contributions are licensed under the MIT License (see [LICENSE](LICENSE)).

---

Questions? Open a discussion at https://github.com/adityabansal98/PolyClaw-Agentic/discussions.
