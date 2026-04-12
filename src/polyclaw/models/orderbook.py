from pydantic import BaseModel


class OrderLevel(BaseModel):
    price: float
    size: float


class OrderBook(BaseModel):
    token_id: str
    market_id: str  # condition_id
    bids: list[OrderLevel]
    asks: list[OrderLevel]
    spread: float | None = None
    midpoint: float | None = None
    best_bid: float | None = None
    best_ask: float | None = None
    timestamp: int  # unix ms from CLOB API
    neg_risk: bool = False

    @classmethod
    def from_clob_summary(cls, summary) -> "OrderBook":
        """Build from py_clob_client.clob_types.OrderBookSummary."""
        bids = [
            OrderLevel(price=float(o.price), size=float(o.size))
            for o in (summary.bids or [])
        ]
        asks = [
            OrderLevel(price=float(o.price), size=float(o.size))
            for o in (summary.asks or [])
        ]
        best_bid = max((b.price for b in bids), default=None)
        best_ask = min((a.price for a in asks), default=None)
        midpoint = (best_bid + best_ask) / 2 if best_bid and best_ask else None
        spread = best_ask - best_bid if best_bid and best_ask else None

        return cls(
            token_id=summary.asset_id,
            market_id=summary.market,
            bids=bids,
            asks=asks,
            best_bid=best_bid,
            best_ask=best_ask,
            midpoint=midpoint,
            spread=spread,
            timestamp=summary.timestamp,
            neg_risk=summary.neg_risk,
        )
