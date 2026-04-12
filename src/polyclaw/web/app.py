import json
import logging
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from polyclaw.clients.clob import ClobClientWrapper
from polyclaw.clients.gamma import GammaClient
from polyclaw.config import settings
from polyclaw.trading.models import Side, TradeOrder, TradeOrderType
from polyclaw.trading.paper_trader import PaperTrader

logger = logging.getLogger(__name__)

app = FastAPI(title="PolyClaw", version="0.1.0")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Shared instances
gamma = GammaClient()
clob = ClobClientWrapper()
trader = PaperTrader(
    db_path=settings.paper_db_path,
    starting_balance=settings.paper_starting_balance,
    clob=clob,
)


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/markets")
async def search_markets(q: str = "", limit: int = Query(default=20, le=100)):
    """Search active markets via Gamma API."""
    import httpx

    params: dict = {"limit": limit, "active": True}
    if q:
        params["tag"] = q

    # Use direct httpx call for the text search since Gamma doesn't have
    # a proper search endpoint — we filter client-side
    all_markets = gamma.get_markets(limit=100)

    if q:
        q_lower = q.lower()
        filtered = [m for m in all_markets if q_lower in m.question.lower()]
    else:
        filtered = all_markets

    # Sort by volume descending
    filtered.sort(key=lambda m: m.volume, reverse=True)

    return [
        {
            "id": m.id,
            "question": m.question,
            "slug": m.slug,
            "outcomes": m.outcomes,
            "outcome_prices": m.outcome_prices,
            "clob_token_ids": m.clob_token_ids,
            "condition_id": m.condition_id,
            "liquidity": m.liquidity,
            "volume": m.volume,
            "volume_24hr": m.volume_24hr,
            "end_date": m.end_date,
            "active": m.active,
            "accepting_orders": m.accepting_orders,
            "neg_risk": m.neg_risk,
            "group_item_title": m.group_item_title,
        }
        for m in filtered[:limit]
    ]


@app.get("/api/orderbook/{token_id}")
async def get_orderbook(token_id: str):
    """Get live orderbook for a token."""
    try:
        ob = clob.get_orderbook(token_id)
        return {
            "token_id": ob.token_id,
            "market_id": ob.market_id,
            "best_bid": ob.best_bid,
            "best_ask": ob.best_ask,
            "spread": ob.spread,
            "midpoint": ob.midpoint,
            "bids": [{"price": l.price, "size": l.size} for l in ob.bids[:15]],
            "asks": [{"price": l.price, "size": l.size} for l in ob.asks[:15]],
        }
    except Exception as e:
        return {"error": str(e)}


class TradeRequest(BaseModel):
    token_id: str
    market_id: str = ""
    question: str = ""
    outcome: str = ""
    side: str  # BUY or SELL
    size: float
    price: float | None = None


@app.post("/api/trade")
async def place_trade(req: TradeRequest):
    """Place a paper trade."""
    order = TradeOrder(
        token_id=req.token_id,
        market_id=req.market_id,
        market_question=req.question,
        outcome=req.outcome,
        side=Side(req.side),
        order_type=TradeOrderType.LIMIT if req.price else TradeOrderType.MARKET,
        price=req.price,
        size=req.size,
    )
    result = trader.place_order(order)
    return {
        "order_id": result.order_id,
        "status": result.status.value,
        "filled_price": result.filled_price,
        "filled_size": result.filled_size,
        "total_cost": result.total_cost,
        "message": result.message,
    }


@app.get("/api/portfolio")
async def get_portfolio():
    """Get paper trading portfolio."""
    p = trader.get_portfolio()
    return {
        "cash_balance": p.cash_balance,
        "total_position_value": p.total_position_value,
        "total_equity": p.total_equity,
        "total_realized_pnl": p.total_realized_pnl,
        "total_unrealized_pnl": p.total_unrealized_pnl,
        "positions": [
            {
                "token_id": pos.token_id,
                "market_id": pos.market_id,
                "market_question": pos.market_question,
                "outcome": pos.outcome,
                "shares": pos.shares,
                "avg_entry_price": pos.avg_entry_price,
                "current_price": pos.current_price,
                "unrealized_pnl": pos.unrealized_pnl,
            }
            for pos in p.positions
        ],
    }


@app.post("/api/reset")
async def reset_portfolio():
    """Reset paper trading."""
    trader.reset()
    return {"message": "Paper trading reset", "balance": settings.paper_starting_balance}
