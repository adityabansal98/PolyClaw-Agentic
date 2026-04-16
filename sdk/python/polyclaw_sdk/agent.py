"""PolyClawAgent — base class for building trading agents.

Subclass and override `decide()` to get auth, logging, retry, rate-limit
handling, and graceful shutdown for free.

    class MyAgent(PolyClawAgent):
        def decide(self):
            portfolio = self.client.get_portfolio()
            if portfolio.cash_balance > 100:
                self.client.place_market_order(
                    token_id="...", market_id="...", side="BUY", usdc=50.0
                )

    MyAgent(base_url="http://localhost:5000", token="polyclaw_live_...").run()
"""

from __future__ import annotations

import logging
import signal
import time
from abc import ABC, abstractmethod

from polyclaw_sdk.client import PolyClawClient

logger = logging.getLogger(__name__)


class PolyClawAgent(ABC):
    """Base class for PolyClaw trading agents.

    Provides a run loop that calls `decide()` on a configurable interval, handles
    signals for graceful shutdown, and wraps the client lifecycle.

    Args:
        base_url: Platform API root URL.
        token: Bearer token from AgentRegistry.
        interval_s: Seconds between `decide()` calls. Default 60.
        name: Optional human-readable name for logging.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        interval_s: float = 60.0,
        name: str | None = None,
    ):
        self.client = PolyClawClient(base_url=base_url, token=token)
        self.interval_s = interval_s
        self.name = name or self.__class__.__name__
        self._running = False

    @abstractmethod
    def decide(self) -> None:
        """Called each tick of the run loop. Implement your strategy here.

        You have full access to `self.client` — use it to read portfolio state,
        fetch market data, place orders, run backtests, etc.
        """
        ...

    def on_start(self) -> None:
        """Optional hook called once before the first `decide()`. Override if you
        need one-time setup (e.g. loading model weights, caching market data)."""

    def on_stop(self) -> None:
        """Optional hook called once after the loop exits. Override for cleanup."""

    def run(self) -> None:
        """Start the agent loop. Blocks until SIGTERM/SIGINT or `stop()` is called."""
        self._running = True
        signal.signal(signal.SIGTERM, lambda *_: self.stop())
        signal.signal(signal.SIGINT, lambda *_: self.stop())

        logger.info("[%s] starting (interval=%.1fs)", self.name, self.interval_s)
        self.on_start()

        try:
            while self._running:
                try:
                    self.decide()
                except Exception:
                    logger.exception("[%s] decide() raised — sleeping and retrying", self.name)
                if self._running:
                    time.sleep(self.interval_s)
        finally:
            self.on_stop()
            self.client.close()
            logger.info("[%s] stopped", self.name)

    def stop(self) -> None:
        self._running = False
