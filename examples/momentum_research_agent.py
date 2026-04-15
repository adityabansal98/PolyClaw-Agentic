"""Reference in-process agent — Phase 2c cookbook example.

The loop this agent runs is the canonical "research-then-trade" flow the platform
is built to serve:

  1. Register the agent (AgentRegistry).
  2. Pick a handful of markets from the active universe.
  3. Enqueue a backtest (BacktestQueue) for a momentum strategy over those markets.
  4. Poll until the worker finishes the backtest.
  5. If the backtested strategy has positive PnL on the winning token, enter a
     real paper trade via TradingService.place_order.

This example uses the in-process path (TradingService + BacktestQueue directly)
rather than hitting the HTTP API. Phase 3's SDK will wrap the same flow in a
`PolyClawAgent` base class that subclasses override. The in-process path still
goes through TradingService, so the RiskGate (once Phase 3 implements it) catches
violations from this agent too — premise P3 holds.

Run with the worker running alongside:
  terminal 1: python -m polyclaw.workers.backtest_worker
  terminal 2: python examples/momentum_research_agent.py

The script is deliberately minimal and synchronous. Production agents should
read the market universe from /api/v1/markets (Phase 3) rather than hardcoding
token_ids, and should handle errors more gracefully than this example.
"""

from __future__ import annotations

import logging
import os
import time

from polyclaw.agents.registry import AgentRegistry, AgentTier
from polyclaw.storage.db import make_engine
from polyclaw.trading.clock import SystemClock
from polyclaw.trading.models import Side, TradeOrder, TradeOrderType
from polyclaw.trading.service import TradingService
from polyclaw.workers.backtest_queue import BacktestQueue

logger = logging.getLogger(__name__)

AGENT_ID = "momentum_research_bot"
STRATEGY = "momentum"  # whatever is registered in polyclaw.backtest.strategies

# In production, this list comes from /api/v1/markets/search. For the example
# we hardcode a sample — swap in real tokens after running backfill_price_ticks.
SAMPLE_MARKETS = [
    {
        "token_id": "REPLACE_WITH_REAL_TOKEN_ID_1",
        "market_id": "REPLACE_WITH_CONDITION_ID_1",
        "question": "Example market 1",
        "outcome": "Yes",
    },
    {
        "token_id": "REPLACE_WITH_REAL_TOKEN_ID_2",
        "market_id": "REPLACE_WITH_CONDITION_ID_2",
        "question": "Example market 2",
        "outcome": "Yes",
    },
]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    url = os.environ.get("POLYCLAW_DATABASE_URL") or "sqlite:///paper_trading.db"
    engine = make_engine(url)
    clock = SystemClock()

    # 1) Register (idempotent — second run returns the same record).
    registry = AgentRegistry(engine, clock=clock)
    registry.create_agent(
        AGENT_ID,
        name="Momentum Research Bot",
        starting_balance=10_000.0,
        tier=AgentTier.HOSTED_INPROCESS,
    )

    svc = TradingService(engine=engine, clock=clock)
    queue = BacktestQueue(engine, clock=clock)

    # 2 + 3) Enqueue the backtest.
    try:
        run_id = queue.enqueue(
            agent_id=AGENT_ID,
            strategy=STRATEGY,
            params={},
            markets=SAMPLE_MARKETS,
            fidelity=60,
            cash=1_000.0,
        )
    except Exception as e:
        logger.error("enqueue failed: %s", e)
        return 1
    logger.info("enqueued backtest %s — waiting for worker to finish it…", run_id)

    # 4) Poll until finished.
    for _ in range(60):
        row = queue.get(run_id)
        if row is None:
            logger.error("backtest row disappeared")
            return 1
        if row["status"] == "finished":
            break
        if row["status"] == "failed":
            logger.error("backtest failed: %s", row.get("error"))
            return 1
        time.sleep(2)
    else:
        logger.error("backtest did not finish in 120s — is the worker running?")
        return 1

    result = row["result"] or {}
    metrics = result.get("metrics", {})
    logger.info("backtest finished: sharpe=%.2f pnl=%.2f", metrics.get("sharpe", 0.0), metrics.get("total_return", 0.0))

    # 5) If the backtest showed positive return, buy into the winning market.
    if metrics.get("total_return", 0.0) > 0 and SAMPLE_MARKETS:
        target = SAMPLE_MARKETS[0]
        order = TradeOrder(
            token_id=target["token_id"],
            market_id=target["market_id"],
            market_question=target["question"],
            outcome=target["outcome"],
            side=Side.BUY,
            order_type=TradeOrderType.MARKET,
            size=50.0,  # USDC
        )
        fill = svc.place_order(AGENT_ID, order)
        logger.info("placed trade: %s", fill)
    else:
        logger.info("no positive-return signal, sitting out this cycle")

    portfolio = svc.get_portfolio(AGENT_ID)
    logger.info(
        "final portfolio: cash=%.2f equity=%.2f positions=%d",
        portfolio.cash_balance,
        portfolio.total_equity,
        len(portfolio.positions),
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
