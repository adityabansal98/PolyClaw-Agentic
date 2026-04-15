from __future__ import annotations

from .agents import Agent
from .pipeline import SelectionPipeline
from .simulation import AgentArenaSimulation


def run_single_tick(
    *,
    pipeline: SelectionPipeline,
    arena: AgentArenaSimulation,
    agents: list[Agent],
    category: str = "NBA",
    limit: int = 800,
    settle_after_seconds: int = 3600,
) -> dict:
    results = pipeline.run_with_public_api(limit=limit)
    output = pipeline.to_output_dict(results)
    category_markets = output.get(category, [])

    market_prices_yes = {
        str(row.get("market_id")): float(row.get("p_market_yes", 0.5) or 0.5)
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
