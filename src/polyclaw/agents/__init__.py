"""Agent identity + portfolio management.

Phase 2b module. The old in-process `Agent` class (polyclaw/agents.py, since deleted)
was coupled to the toy coin arena — scored a single pre-picked market and returned
{should_bet, stake, side}. It doesn't survive the move to real multi-tenant portfolios
through `TradingService`.

Contents:
- `AgentRegistry`     — CRUD over `agents` + `agent_keys`, bearer-key issuance + verify
- `PortfolioManager`  — cached `PaperTrader(agent_id=...)` factory, shared by the
                        HTTP path and in-process agents so they go through the same
                        code path (premise P3 holds)
"""

from polyclaw.agents.portfolio_manager import PortfolioManager
from polyclaw.agents.registry import AgentRecord, AgentRegistry, AgentTier

__all__ = ["AgentRecord", "AgentRegistry", "AgentTier", "PortfolioManager"]
