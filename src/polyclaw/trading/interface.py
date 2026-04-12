from abc import ABC, abstractmethod

from polyclaw.trading.models import (
    OrderResult,
    PortfolioSummary,
    Position,
    TradeOrder,
)


class TraderInterface(ABC):
    """Common interface for live and paper trading.

    Your betting agent should program against this interface,
    then swap implementations via config (mode = "paper" | "live").
    """

    @abstractmethod
    def place_order(self, order: TradeOrder) -> OrderResult:
        """Submit a trade order. Returns fill result."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order. Returns True if successfully cancelled."""
        ...

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """Get all current positions."""
        ...

    @abstractmethod
    def get_portfolio(self) -> PortfolioSummary:
        """Get full portfolio summary with PnL."""
        ...

    @abstractmethod
    def get_balance(self) -> float:
        """Get available cash balance (USDC)."""
        ...
