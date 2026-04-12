from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from polyclaw.trading.models import Side


@dataclass
class TickContext:
    """Everything a strategy sees at each tick."""
    timestamp: int
    token_id: str
    market_id: str
    market_question: str
    price: float
    prices: list[float]       # all prices up to this tick (no look-ahead)
    cash: float
    position_shares: float
    avg_entry_price: float
    tick_index: int
    total_ticks: int


@dataclass
class Signal:
    """A trading signal emitted by a strategy."""
    side: Side
    size: float               # USDC for BUY, shares for SELL
    reason: str = ""


class Strategy(ABC):
    """Base class for backtesting strategies.

    Subclass and implement on_tick(). Return a Signal to trade, or None to hold.
    """

    name: str = "unnamed"

    def configure(self, params: dict) -> None:
        """Receive user-supplied parameters before the backtest starts."""
        for key, value in params.items():
            if hasattr(self, key):
                setattr(self, key, value)

    @abstractmethod
    def on_tick(self, ctx: TickContext) -> Signal | None:
        """Called once per price tick per market. Return Signal or None."""
        ...

    def on_backtest_start(self) -> None:
        pass

    def on_backtest_end(self) -> None:
        pass
