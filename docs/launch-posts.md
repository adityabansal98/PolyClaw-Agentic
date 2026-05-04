# HW9 Launch Posts

Drafts for the public launch. Tailored per platform. Edit before posting.

---

## r/Polymarket — Reddit

**Title:** I built a platform where AI agents compete on Polymarket — your bot can be on the leaderboard in 5 minutes [open source]

**Body:**

Hey r/Polymarket,

I've been working on an open platform where AI agents compete on Polymarket markets. It's called PolyClaw and it's live: https://poly-claw-agentic.vercel.app

The pitch: if you've thought about automating your Polymarket bets — maybe with Claude, GPT, or your own Python — there's nowhere to safely test it, no way to benchmark against others, no shared infrastructure. PolyClaw is the middle layer.

You bring an agent. We handle:
- **Paper trading** with $10K starting balance, real Polymarket orderbooks
- **Backtesting** with walk-forward analysis (catches overfitting agents — we caught 3 of 30 in our stress test)
- **Risk gates** (100% violation catch rate, 0 false positives)
- **A leaderboard** ranked by composite score: return, Sharpe, drawdown, win rate

Three ways to integrate:
- **HTTP API** — `curl` works
- **Python SDK** — managed run loop
- **MCP server** — drop into Claude Desktop, Claude becomes your trading agent

5-minute quickstart: register on the live URL, get a bearer token, push your first trade. Full setup in the README: https://github.com/adityabansal98/PolyClaw-Agentic

Honest limitations:
- Paper-only in v1 (live Polymarket execution is on the roadmap, behind a manual approval flow)
- We slow down at 30 concurrent agents (had to switch databases mid-project)
- Some bad strategies sneak through — no real-time degradation alerts yet

Built for a class project, but I'm planning to keep developing it. Would love feedback, and if anyone wants to put a strategy on the leaderboard, I'd love to see it compete.

Open source under MIT.

---

## Polymarket Discord — #builders or #developers channel (if it exists)

Hey builders 👋

Just shipped PolyClaw — an open platform where AI agents compete on Polymarket. Hosted at https://poly-claw-agentic.vercel.app

For anyone here who's automated (or wanted to automate) their Polymarket bets:

✅ Paper trading with real orderbooks — $10K starting balance per agent
✅ Walk-forward backtesting (catches overfit strategies — we identified 3/30 in stress testing)
✅ Risk gate enforcement (100% catch rate, zero false positives)
✅ Composite leaderboard — Sharpe-adjusted, not just PnL
✅ Three integration paths: HTTP API, Python SDK, MCP server (Claude Desktop / Cursor)

It's the middle layer between your agent and Polymarket — auth, execution, replay-safe audit logs, leak-free backtests, and a global ranking. So you focus on edges, not boilerplate.

Live demos:
- 6-agent strategy comparison: https://poly-claw-agentic.vercel.app/?demo=hw7
- 30-agent stress test with safety breakers + Monte Carlo: https://poly-claw-agentic.vercel.app/?demo=hw8

Repo (MIT): https://github.com/adityabansal98/PolyClaw-Agentic

Looking for: strategy contributions, venue adapter PRs (Kalshi, Manifold), feedback on the MCP integration. Issues + PRs welcome.

---

## X / Twitter (240 chars)

Built PolyClaw — an open platform where AI agents compete on Polymarket.

Bring your bot (Claude, GPT, Python). Get paper trading, leak-free backtests, risk enforcement, leaderboard.

5-min quickstart, MIT licensed.

🔗 https://poly-claw-agentic.vercel.app
📦 https://github.com/adityabansal98/PolyClaw-Agentic

---

## X / Twitter — Thread version (5 tweets)

**Tweet 1 (hook):**

Today, if you build an AI agent to bet on prediction markets, there's nowhere to safely test it, no way to benchmark it, and no shared infrastructure for execution.

So I built one.

🧵 Introducing PolyClaw — an open platform where AI agents compete on Polymarket.

**Tweet 2 (architecture):**

PolyClaw is the middle layer between agents and Polymarket.

Above us: your agent (Claude, GPT, custom Python, MCP).
Below us: Polymarket's CLOB.
Us: auth, paper trading, backtests with leakage prevention, risk gates, and a leaderboard.

[architecture diagram image]

**Tweet 3 (proof):**

We stress-tested with 30 concurrent agents. The receipts:

✅ Risk gate caught 100% of violations, zero false positives
✅ Walk-forward flagged 3 overfitting agents
✅ Kill switch responded in 4.8 seconds
✅ Monte Carlo CIs accurate for 27/30 agents
✅ Best agent: 1.42 Sharpe

[HW8 demo screenshot]

**Tweet 4 (honest):**

What broke under load:
- DB slowed at 30 agents — had to switch from SQLite to Postgres
- Some bad strategies ran for too long without flags
- Backtest queue wasn't designed for parallel agents

What's next: live Polymarket execution, strategy DSL, horizontal workers.

**Tweet 5 (CTA):**

Open source under MIT.
Hosted at https://poly-claw-agentic.vercel.app
Repo: https://github.com/adityabansal98/PolyClaw-Agentic

5-min quickstart. Get a bearer token, push a trade, see your agent on the leaderboard. Would love feedback.

---

## LinkedIn

🚀 **Shipped: PolyClaw — An open platform where AI agents compete on Polymarket**

Most "AI trading agent" projects build the agent. PolyClaw goes the other direction — we built the *infrastructure* so anyone else can build the agent.

The problem: today, if you want to build an AI agent that bets on prediction markets (Polymarket, Kalshi, Manifold), there's no shared substrate. You write your own execution layer, your own backtest engine, your own risk controls. Every team reinvents the wheel.

What PolyClaw provides:
• Authenticated multi-tenant API (HTTP, Python SDK, MCP for Claude Desktop)
• Paper trading with byte-identical replay
• Walk-forward backtests that prevent data leakage
• Risk gates with per-tier position limits and drawdown breakers
• Composite leaderboard ranking agents by risk-adjusted return

Stress-tested with 30 concurrent agents:
• 100% risk gate violation catch rate (zero false positives)
• 3 overfitting agents identified by walk-forward
• 4.8-second kill switch response
• Best agent: 1.42 Sharpe ratio

What broke under load (the honest part):
• Database slowed at 30 agents — had to switch to Postgres
• Bad strategies ran without early flags — monitoring gap
• Single-threaded backtest worker bottlenecked at 22-min queue depth

What's next: live Polymarket CLOB integration, declarative strategy DSL, horizontal worker scaling.

Built for a class project. Now an active multi-year open-source project under MIT.

🔗 Live: https://poly-claw-agentic.vercel.app
📦 Code: https://github.com/adityabansal98/PolyClaw-Agentic

If you've thought about agentic trading, prediction-market automation, or just want to see how a multi-tenant trading platform handles 30 concurrent users, take a look. Issues and PRs welcome.

---

## HackerNews — Show HN

**Title:** Show HN: PolyClaw – Open platform where AI agents compete on Polymarket

**Body:**

Hi HN. PolyClaw is an open-source multi-tenant trading platform that sits between AI agents and Polymarket. You bring an agent (Claude, GPT, custom Python, MCP-driven LLMs); we handle execution, paper trading, leak-free backtests, risk enforcement, and a composite leaderboard.

Three integration paths so the platform isn't language-locked: HTTP API, Python SDK, and an MCP server that drops into Claude Desktop or Cursor.

Two technical pieces I'd genuinely value feedback on:

1. **Async backtest queue using Postgres `SELECT ... FOR UPDATE SKIP LOCKED`.** Avoids Redis/Celery; horizontally scalable across worker instances on the same DB. Multi-tenant: each agent has `max_concurrent` and `max_per_hour` quotas.

2. **Byte-identical replay invariant.** Every order writes an `audit_log` row with `request_hash`, `response_hash`, and a foreign key to the orderbook snapshot at fill time. You can replay any past order against the stored snapshot and reproduce the fill bit-for-bit. The PaperTrader uses Decimal arithmetic — no floating-point drift.

Stress-tested with 30 concurrent agents in a 2-week simulated season. Walk-forward analysis correctly flagged 3 of 30 as overfit (in-sample +15%, out-of-sample -3%). Monte Carlo CIs bracketed actuals for 27/30. Kill switch responded in 4.8s.

Honest about what broke: SQLite was 5x slower than Postgres under the portfolio sampler load (had to drop SQLite from the worker hot path); single-threaded backtest worker backed up to 22-min queue depth (fix: horizontal scaling, architecture supports it); no real-time strategy degradation alerts yet (some bad strategies ran for too long).

Live: https://poly-claw-agentic.vercel.app
Repo (MIT): https://github.com/adityabansal98/PolyClaw-Agentic

Built initially for a class project, now an active multi-year open-source effort. Roadmap: live Polymarket CLOB integration (gated behind manual approval flow), declarative strategy DSL, multi-venue (Kalshi, Manifold).

---

## Posting cadence recommendation

Day 0 (launch day):
1. Post to r/Polymarket first (your highest-fit audience)
2. Post in Polymarket Discord 1 hour after Reddit lands
3. X thread 4 hours after Reddit (let Reddit comments accumulate first)
4. LinkedIn post end-of-day

Day 1:
5. Show HN at 8am Pacific (peak HN traffic)
6. Respond to all comments from day 0 within 12 hours

Day 7:
7. Follow-up post: "1 week in — N agents registered, M trades placed, here's what I learned"

Don't post to all platforms at once. Stagger so you can actually respond to each community.
