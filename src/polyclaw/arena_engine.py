from __future__ import annotations

from polyclaw.agents import Agent
from polyclaw.simulation import AgentArenaSimulation
from polyclaw.web.strategy_service import get_scored_opportunities


def run_single_tick(
    *,
    arena: AgentArenaSimulation,
    agents: list[Agent],
    category: str = "NBA",
    limit: int = 800,
    settle_after_seconds: int = 3600,
) -> dict:
    _ = limit  # limit is currently controlled by strategy service internals.
    picks = get_scored_opportunities()
    category_markets = [row for row in picks if str(row.get("category")) == category]

    market_prices_yes = {
        str(row.get("market_id")): float(row.get("p_market_yes", row.get("yesPrice", 0.5)) or 0.5)
        for row in category_markets
        if row.get("market_id")
    }

    for recommendation in category_markets:
        for agent in agents:
            balance = arena.get_agent_balance(agent.name)
            decision = agent.decide_bet(recommendation, balance=balance)
            if not decision.should_bet or decision.stake <= 0:
                continue
            arena.record_bet(
                agent_name=agent.name,
                recommendation=recommendation,
                side=decision.side or str(recommendation.get("side", "YES")),
                stake=decision.stake,
            )

    arena.settle_open_bets(market_prices_yes, min_age_seconds=settle_after_seconds)
    return arena.export_state(markets=category_markets)
