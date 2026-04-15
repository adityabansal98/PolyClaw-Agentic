from enum import Enum

from pydantic import BaseModel


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TradeOrderType(str, Enum):
    MARKET = "MARKET"  # FOK — fill or kill
    LIMIT = "LIMIT"  # GTC — good till cancelled


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class TradeOrder(BaseModel):
    """A trade order submitted to either live or paper engine."""

    token_id: str
    market_id: str  # condition_id
    market_question: str = ""
    outcome: str = ""  # "Yes" or "No"
    side: Side
    order_type: TradeOrderType
    price: float | None = None  # required for LIMIT, auto for MARKET
    size: float  # number of shares for LIMIT; USDC amount for MARKET BUY, shares for MARKET SELL


class OrderResult(BaseModel):
    """Result after submitting an order."""

    order_id: str
    status: OrderStatus
    filled_price: float | None = None
    filled_size: float | None = None
    total_cost: float | None = None  # USDC spent (buys) or received (sells)
    message: str = ""


class Position(BaseModel):
    """A current holding in a market outcome."""

    token_id: str
    market_id: str
    market_question: str = ""
    outcome: str = ""
    shares: float
    avg_entry_price: float
    current_price: float | None = None
    unrealized_pnl: float | None = None


class PortfolioSummary(BaseModel):
    """Overall portfolio state."""

    cash_balance: float
    positions: list[Position]
    total_position_value: float
    total_equity: float  # cash + position value
    total_realized_pnl: float
    total_unrealized_pnl: float
