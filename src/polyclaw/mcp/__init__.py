"""PolyClaw MCP server — Phase 3c.

Exposes agent tools via the Model Context Protocol (stdio transport) so Claude
Desktop, Cursor, and other MCP-capable hosts can trade, browse markets, run
backtests, and check the leaderboard through natural language.

Tool names and descriptions are DISTINCT from the OpenAPI surface — they're
curated for LLM consumption, not 1:1 pass-throughs. Errors are reshaped into
human-readable explanations instead of raw {code, details} JSON.
"""
