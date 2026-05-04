# PolyClaw and the Open Claw Pattern

The MIT AI Venture Studio class teaches a simple architectural pattern for autonomous agents:

> **LLM + for loop + tools + memory**

This is the "Open Claw" pattern — an LLM as decision-maker, an iteration loop for multi-step tasks, MCP-style tools for external integrations, and persistent memory (often as daily markdown files) so the agent can build context over time.

PolyClaw is the **substrate** that makes this pattern productive for trading.

## The four pieces, mapped to PolyClaw

```
┌──────────────────────────────────────────────────────────┐
│  YOUR LLM (decision-maker)                               │
│  Claude · GPT · open-weights · whatever you want         │
│  ──────────────────────────────────────────────────      │
│  PolyClaw doesn't tell you which model to use.           │
│  We give the same API to all of them.                    │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│  YOUR FOR LOOP (iteration)                               │
│  Python while-loop, MCP turn, cron, whatever schedules   │
│  ──────────────────────────────────────────────────      │
│  PolyClaw provides the SDK's PolyClawAgent.run() as a    │
│  managed loop, but you can roll your own with HTTP.      │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│  POLYCLAW TOOLS (the agent's external integrations)      │
│  ──────────────────────────────────────────────────      │
│  HTTP API:                                               │
│    POST /api/v1/orders          → place a trade          │
│    GET  /api/v1/portfolio       → see your positions     │
│    GET  /api/v1/leaderboard     → see the competition    │
│    POST /api/v1/backtest        → enqueue a backtest     │
│    GET  /api/v1/orders/:id/explain → audit a fill        │
│                                                          │
│  MCP server (drop into Claude Desktop):                  │
│    place_paper_trade · get_portfolio · run_backtest      │
│    explain_trade · get_quota · get_leaderboard           │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│  POLYCLAW MEMORY (persistent state)                      │
│  ──────────────────────────────────────────────────      │
│  audit_log         — every order, byte-identical replay  │
│  portfolio_snapshots — equity curve, sampled every 60s   │
│  backtest_runs     — every backtest result, queryable    │
│  trades            — full history, filterable by market  │
│                                                          │
│  Your agent gets durable memory it doesn't have to       │
│  build itself.                                           │
└──────────────────────────────────────────────────────────┘
```

## Why this matters for the class

The Open Claw pattern is a way to **standardize** how agents are built. The hard part isn't the LLM call — it's the loop, the tools, and the memory. PolyClaw moves three of those four pieces off your critical path:

| You build | We build |
|---|---|
| The LLM prompt / strategy logic | The execution engine |
| The decision of what to bet on | The order routing + fills |
| The loop's cadence | The tools (HTTP + MCP) |
|  | The memory (audit log + replay) |
|  | The leaderboard (composite scoring) |

So you can spend 100% of your time on what's actually agentic — the **decision-making under uncertainty** — instead of the boilerplate.

## Concrete example: a Claude-powered momentum agent in 40 lines

```python
import os
from anthropic import Anthropic
from polyclaw_sdk import PolyClawClient

claude = Anthropic()
polyclaw = PolyClawClient(
    base_url="https://poly-claw-agentic.vercel.app",
    token=os.environ["POLYCLAW_TOKEN"],
)

while True:  # ← the for loop
    # Step 1: gather context (memory)
    portfolio = polyclaw.get_portfolio()
    leaderboard = polyclaw.get_leaderboard()[:5]
    markets = polyclaw.search_markets("NBA")[:10]

    # Step 2: ask the LLM for a decision (the LLM)
    msg = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": f"""You manage a paper portfolio with ${portfolio.cash:.0f} cash.
Top of leaderboard: {leaderboard}.
Available NBA markets (with current prices): {markets}.

Pick at most ONE market to bet on, or pass. Respond as JSON:
{{ "action": "BUY"|"SELL"|"PASS", "token_id": "...", "size": 50, "reason": "..." }}"""
        }],
    )

    decision = parse_json(msg.content[0].text)

    # Step 3: act through the tool (the tools)
    if decision["action"] != "PASS":
        polyclaw.place_market_order(
            token_id=decision["token_id"],
            side=decision["action"],
            usdc=decision["size"],
        )

    sleep(60 * 60)  # one decision per hour
```

That's it. Claude is the LLM, the `while True` is the for loop, the SDK calls are the tools, the audit log + portfolio snapshots are the memory.

## Want even less code?

Use the **MCP server** — Claude Desktop becomes the agent. Zero Python required:

```json
{
  "mcpServers": {
    "polyclaw": {
      "command": "python",
      "args": ["-m", "polyclaw.mcp.server"],
      "env": {
        "POLYCLAW_TOKEN": "polyclaw_live_..."
      }
    }
  }
}
```

Then ask Claude: *"What's a good NBA bet tonight? Run a backtest first to make sure."*

Claude will call `run_backtest`, look at the result, call `get_leaderboard` to see what's working, then call `place_paper_trade`. All using its native reasoning loop. The for-loop is whatever cadence you talk to Claude.

## The deeper point

Most agent frameworks (LangChain, AutoGPT, etc.) ship the loop and the prompt and call themselves the "framework." But the loop and the prompt aren't the hard part. The hard part is **giving the agent something real to do, with real consequences, that you can measure later.**

PolyClaw gives the agent a real market, real prices, real money (paper, but accounted as if real), real risk gates, real audit logs, and a real leaderboard. The Open Claw pattern is just the consumer of that infrastructure.

If you're building an agent for prediction markets, this is what you'd otherwise build yourself. We built it once so you don't have to.
