"""PortfolioManager — cached `PaperTrader(agent_id=...)` factory.

Why this exists:

- TradingService wants to dispatch `place_order(agent_id, ...)` to a PaperTrader
  bound to that agent_id. Building a new PaperTrader per call is cheap-ish, but
  the fee-rate cache lives on the instance and would be thrown away each time.

- This class owns the `agent_id -> PaperTrader` map. One Engine + one Clock +
  one MarketDataProvider are shared across all agents; only the per-agent state
  differs.

- In-process agents and the HTTP path share the same PortfolioManager so premise
  P3 holds: there is no privileged in-process backdoor. The only difference is
  who calls TradingService.
"""

from __future__ import annotations

from sqlalchemy import Engine

from polyclaw.trading.clock import Clock, SystemClock
from polyclaw.trading.market_data import LiveMarketDataProvider, MarketDataProvider
from polyclaw.trading.paper_trader import PaperTrader


class PortfolioManager:
    def __init__(
        self,
        engine: Engine,
        *,
        clock: Clock | None = None,
        market_data: MarketDataProvider | None = None,
    ):
        self.engine = engine
        self.clock: Clock = clock or SystemClock()
        self.market_data: MarketDataProvider = market_data or LiveMarketDataProvider()
        self._traders: dict[str, PaperTrader] = {}

    def trader_for(self, agent_id: str) -> PaperTrader:
        """Return (or lazily create) the PaperTrader bound to `agent_id`.

        Assumes the agent row already exists in the registry. PaperTrader's own
        `ensure_agent_row` seeding is the backstop: if the registry hasn't created
        the row, the PaperTrader constructor will seed `paper_config.cash_balance`
        with the default starting balance (10_000). Prefer explicit
        `AgentRegistry.create_agent` so the balance is authoritative.
        """
        trader = self._traders.get(agent_id)
        if trader is None:
            trader = PaperTrader(
                agent_id=agent_id,
                engine=self.engine,
                clock=self.clock,
                market_data=self.market_data,
            )
            self._traders[agent_id] = trader
        return trader

    def forget(self, agent_id: str) -> None:
        """Drop the cached PaperTrader for this agent. Useful after reset/destroy."""
        self._traders.pop(agent_id, None)
