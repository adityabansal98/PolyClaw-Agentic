"""TradingService — single chokepoint for all order writes. Phase 2b.

Both HTTP callers (Phase 3 middleware) and in-process agents call this. The old
path where in-process code constructed `PaperTrader(...)` directly is gone: every
write-facing call now goes through `TradingService.place_order(agent_id, order)`.

Why this shape:

- Per eng review: RiskGate (Phase 3) hooks INTO TradingService, not HTTP middleware.
  If the gate lived in middleware, in-process agents would bypass it and premise P1
  would be violated. By putting the gate at this layer, both paths hit the same
  check with identical error contracts.

- Read-only calls (`get_portfolio`, `get_positions`, etc.) dispatch through here too
  so that dashboard code doesn't hold a long-lived PaperTrader reference and accidentally
  bypass future rate-limiting / audit hooks on reads.

- The RiskGate is a no-op today (`_check_risk` returns the order unchanged). Phase 3
  replaces the body with real checks. The method exists now so the call site is stable.
"""

from __future__ import annotations

import logging

from sqlalchemy import Engine

from polyclaw.agents.portfolio_manager import PortfolioManager
from polyclaw.trading.clock import Clock, SystemClock
from polyclaw.trading.market_data import LiveMarketDataProvider, MarketDataProvider
from polyclaw.trading.models import (
    OrderResult,
    PortfolioSummary,
    Position,
    TradeOrder,
)

logger = logging.getLogger(__name__)


class TradingService:
    """The single chokepoint for paper trading reads + writes.

    Construct one per process, share across HTTP handlers and in-process agents. All
    methods are thread-safe as far as the underlying engine allows (cash debits are
    serialized inside PaperTrader via BEGIN IMMEDIATE / SELECT FOR UPDATE).
    """

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
        self.portfolios = PortfolioManager(engine=engine, clock=self.clock, market_data=self.market_data)

    # ── Writes ─────────────────────────────────────────────────

    def place_order(
        self,
        agent_id: str,
        order: TradeOrder,
        *,
        request_id: str | None = None,
    ) -> OrderResult:
        """Submit an order on behalf of `agent_id`. Runs the risk gate (no-op today,
        real in Phase 3), then dispatches to the cached PaperTrader for this agent."""
        self._check_risk(agent_id, order)
        trader = self.portfolios.trader_for(agent_id)
        return trader.place_order(order, request_id=request_id)

    def cancel_order(self, agent_id: str, order_id: str) -> bool:
        return self.portfolios.trader_for(agent_id).cancel_order(order_id)

    # ── Reads ──────────────────────────────────────────────────

    def get_portfolio(self, agent_id: str) -> PortfolioSummary:
        return self.portfolios.trader_for(agent_id).get_portfolio()

    def get_positions(self, agent_id: str) -> list[Position]:
        return self.portfolios.trader_for(agent_id).get_positions()

    def get_balance(self, agent_id: str) -> float:
        return self.portfolios.trader_for(agent_id).get_balance()

    def get_trade_history(self, agent_id: str) -> list[dict]:
        return self.portfolios.trader_for(agent_id).get_trade_history()

    def reset(self, agent_id: str) -> None:
        self.portfolios.trader_for(agent_id).reset()
        self.portfolios.forget(agent_id)

    # ── RiskGate hook (Phase 3) ────────────────────────────────

    def _check_risk(self, agent_id: str, order: TradeOrder) -> None:
        """RiskGate hook. No-op in Phase 2b — Phase 3 replaces the body with real
        checks (per-tier order size caps, rate limits, max position size, etc.) and
        raises a structured RiskGateError that the HTTP middleware turns into the
        `risk_gate.*` error code family.

        Kept as a stub so the call site is stable and tests can monkeypatch in real
        checks without changing the TradingService API surface.
        """
        _ = agent_id, order  # intentionally unused until Phase 3
