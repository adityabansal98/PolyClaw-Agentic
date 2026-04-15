from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from polyclaw.agents import load_agents_from_config
from polyclaw.arena_engine import run_single_tick
from polyclaw.simulation import AgentArenaSimulation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentArena: multi-agent NBA paper betting simulator.")
    parser.add_argument("--agent-config", type=str, default="data/agent_config.json")
    parser.add_argument("--db-path", type=str, default="data/agent_arena.db")
    parser.add_argument("--state-path", type=str, default="data/agent_arena_state.json")
    parser.add_argument("--limit", type=int, default=800, help="Number of live markets to pull each cycle.")
    parser.add_argument("--tick-seconds", type=int, default=300, help="Loop interval in seconds.")
    parser.add_argument("--settle-after-seconds", type=int, default=3600, help="Minimum open duration before settlement.")
    parser.add_argument("--starting-balance", type=float, default=1000.0)
    parser.add_argument(
        "--category",
        type=str,
        default="NBA",
        help="Single category to simulate (default: NBA).",
    )
    return parser


async def run_loop(args) -> None:
    agents = load_agents_from_config(args.agent_config)
    arena = AgentArenaSimulation(
        db_path=args.db_path,
        state_path=args.state_path,
        starting_balance=args.starting_balance,
    )
    for agent in agents:
        arena.ensure_agent(agent.name)

    target_category = str(args.category or "NBA")
    logging.info("Starting AgentArena with %d agents on category=%s.", len(agents), target_category)
    while True:
        try:
            state = run_single_tick(
                arena=arena,
                agents=agents,
                category=target_category,
                limit=args.limit,
                settle_after_seconds=args.settle_after_seconds,
            )
            logging.info(
                "Tick complete: category=%s markets=%d active_bets=%d",
                target_category,
                len(state.get("markets", [])),
                len(state.get("active_bets", [])),
            )
        except Exception:
            logging.exception("AgentArena tick failed")

        await asyncio.sleep(args.tick_seconds)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args()
    Path(args.agent_config).parent.mkdir(parents=True, exist_ok=True)
    try:
        asyncio.run(run_loop(args))
    except KeyboardInterrupt:
        logging.info("AgentArena stopped.")


if __name__ == "__main__":
    main()
