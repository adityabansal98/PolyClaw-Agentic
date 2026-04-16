"""MCP tool server for PolyClaw — stdio transport.

Curated tool surface designed for LLM hosts (Claude Desktop, Cursor). Tool names
are short verbs, descriptions include parameter examples, and errors are
reshaped into complete sentences rather than raw JSON.

Start with:
    python -m polyclaw.mcp.server

Or configure in Claude Desktop's config.json (see docs/mcp/claude_desktop.json).

Environment variables:
    POLYCLAW_MCP_BEARER_TOKEN  — bearer token for the agent this MCP session acts as
    POLYCLAW_MCP_BASE_URL      — API root (default: http://localhost:5000)
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any


def _client():
    """Lazy-build a PolyClawClient from env vars."""
    # Inline import so the module loads without the SDK installed in the
    # main polyclaw venv — the MCP server only needs httpx + pydantic.
    sdk_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "sdk", "python")
    if sdk_path not in sys.path:
        sys.path.insert(0, os.path.abspath(sdk_path))
    from polyclaw_sdk import PolyClawClient

    return PolyClawClient(
        base_url=os.environ.get("POLYCLAW_MCP_BASE_URL", "http://localhost:5000"),
        token=os.environ.get("POLYCLAW_MCP_BEARER_TOKEN", ""),
    )


# ── Tool implementations ──────────────────────────────────────────────────
# Each function returns a dict that the MCP stdio handler serializes as the
# tool result. Errors are caught and returned as human-readable strings.


def polyclaw_get_started() -> dict[str, Any]:
    """Get a grounding overview: your portfolio + 3 recent trades + leaderboard position.

    Call this first in any conversation about PolyClaw to understand your current state.
    No parameters needed.
    """
    client = _client()
    try:
        portfolio = client.get_portfolio()
        trades = client.get_trades()[:3]
        leaderboard = client.get_leaderboard()
        return {
            "portfolio": portfolio.model_dump(),
            "recent_trades": trades,
            "leaderboard_summary": {
                "total_agents": len(leaderboard.get("items", [])),
                "top_3": leaderboard.get("items", [])[:3],
            },
        }
    except Exception as e:
        return {"error": f"Could not load overview: {e}. Is the API running and your token valid?"}


def place_paper_trade(
    token_id: str,
    market_id: str,
    side: str = "BUY",
    usdc: float = 10.0,
    outcome: str = "Yes",
) -> dict[str, Any]:
    """Place a paper trade. Example: place_paper_trade(token_id="abc123", market_id="mkt456", side="BUY", usdc=50)

    Args:
        token_id: The CLOB token ID (e.g. "0x1234..."). Get this from browse_markets.
        market_id: The condition ID / market ID.
        side: "BUY" or "SELL".
        usdc: How much USDC to spend (for buys) or shares to sell.
        outcome: "Yes" or "No".
    """
    client = _client()
    try:
        result = client.place_market_order(token_id, market_id, side=side, usdc=usdc, outcome=outcome)
        return {
            "status": result.status,
            "filled_price": result.filled_price,
            "filled_size": result.filled_size,
            "total_cost": result.total_cost,
            "order_id": result.order_id,
        }
    except Exception as e:
        return {"error": str(e)}


def get_portfolio() -> dict[str, Any]:
    """Get your current portfolio: cash balance, positions, equity, PnL."""
    client = _client()
    try:
        return client.get_portfolio().model_dump()
    except Exception as e:
        return {"error": str(e)}


def get_leaderboard() -> dict[str, Any]:
    """Get the current agent leaderboard ranked by return %."""
    client = _client()
    try:
        return client.get_leaderboard()
    except Exception as e:
        return {"error": str(e)}


def run_backtest(strategy: str, markets: list[dict], cash: float = 1000.0) -> dict[str, Any]:
    """Enqueue a backtest and wait for the result.

    Args:
        strategy: Strategy name (e.g. "momentum", "mean_reversion"). Use get_strategies for the list.
        markets: List of {token_id, market_id, question, outcome} dicts.
        cash: Starting cash for the backtest (default $1000).
    """
    client = _client()
    try:
        enq = client.enqueue_backtest(strategy=strategy, markets=markets, cash=cash)
        run = client.wait_for_backtest(enq.backtest_id, timeout_s=60)
        if run.status == "failed":
            return {"status": "failed", "error": run.error}
        return {"status": "finished", "metrics": (run.result or {}).get("metrics", {})}
    except Exception as e:
        return {"error": str(e)}


def explain_trade(order_id: str) -> dict[str, Any]:
    """Explain a specific trade: what orderbook the agent saw, the fill details, the audit trail.

    Args:
        order_id: The order ID from a previous trade (e.g. from place_paper_trade result).
    """
    client = _client()
    try:
        return client.explain_order(order_id)
    except Exception as e:
        return {"error": str(e)}


def get_quota() -> dict[str, Any]:
    """Check your current rate limits and usage headroom."""
    client = _client()
    try:
        return client.get_quota().model_dump()
    except Exception as e:
        return {"error": str(e)}


# ── MCP stdio server ─────────────────────────────────────────────────────
# Minimal stdio-based MCP transport. Reads JSON-RPC from stdin, dispatches to
# the tool functions above, writes results to stdout. Compatible with Claude
# Desktop's MCP host protocol.

TOOLS = {
    "polyclaw_get_started": polyclaw_get_started,
    "place_paper_trade": place_paper_trade,
    "get_portfolio": get_portfolio,
    "get_leaderboard": get_leaderboard,
    "run_backtest": run_backtest,
    "explain_trade": explain_trade,
    "get_quota": get_quota,
}

TOOL_SCHEMAS = [
    {
        "name": "polyclaw_get_started",
        "description": "Get a grounding overview: portfolio + recent trades + leaderboard. Call first.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "place_paper_trade",
        "description": "Place a paper trade. Example: side=BUY, usdc=50.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "token_id": {"type": "string", "description": "CLOB token ID"},
                "market_id": {"type": "string", "description": "Market / condition ID"},
                "side": {"type": "string", "enum": ["BUY", "SELL"], "default": "BUY"},
                "usdc": {"type": "number", "description": "USDC amount", "default": 10},
                "outcome": {"type": "string", "enum": ["Yes", "No"], "default": "Yes"},
            },
            "required": ["token_id", "market_id"],
        },
    },
    {
        "name": "get_portfolio",
        "description": "Get current portfolio: cash, positions, equity, PnL.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_leaderboard",
        "description": "Get the agent leaderboard ranked by return %.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "run_backtest",
        "description": "Run a backtest with a strategy and market list. Returns metrics.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "strategy": {"type": "string", "description": "Strategy name (e.g. 'momentum')"},
                "markets": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of {token_id, market_id, question, outcome}",
                },
                "cash": {"type": "number", "default": 1000},
            },
            "required": ["strategy", "markets"],
        },
    },
    {
        "name": "explain_trade",
        "description": "Explain a trade's audit trail: orderbook snapshot, fill, decision.",
        "inputSchema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "get_quota",
        "description": "Check rate limits and usage headroom.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]


def _handle_message(msg: dict) -> dict:
    method = msg.get("method", "")
    msg_id = msg.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "polyclaw", "version": "0.1.0"},
            },
        }

    if method == "notifications/initialized":
        return {}  # no response needed

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOL_SCHEMAS}}

    if method == "tools/call":
        params = msg.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        fn = TOOLS.get(tool_name)
        if fn is None:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}]},
            }
        try:
            result = fn(**arguments)
            text = json.dumps(result, indent=2, default=str)
        except Exception as e:
            text = f"Tool error: {e}"
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"content": [{"type": "text", "text": text}]},
        }

    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}


def main():
    """Run the MCP stdio server. Reads JSON-RPC lines from stdin, writes to stdout."""
    import logging

    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = _handle_message(msg)
        if response:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
