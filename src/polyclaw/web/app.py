import logging
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_from_directory

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
FRONTEND_BUILD_DIR = STATIC_DIR / "app"

app = Flask(__name__, static_folder=str(STATIC_DIR))

# Lazy singletons
_gamma = None
_clob = None
_trader = None


def get_gamma():
    global _gamma
    if _gamma is None:
        from polyclaw.clients.gamma import GammaClient

        _gamma = GammaClient()
    return _gamma


def get_clob():
    global _clob
    if _clob is None:
        from polyclaw.clients.clob import ClobClientWrapper

        _clob = ClobClientWrapper()
    return _clob


def get_trader():
    global _trader
    if _trader is None:
        from polyclaw.config import settings
        from polyclaw.trading.paper_trader import PaperTrader

        _trader = PaperTrader(
            db_path=settings.paper_db_path,
            starting_balance=settings.paper_starting_balance,
            clob=get_clob(),
        )
    return _trader


def frontend_entry_dir() -> Path:
    """Return the compiled React app when available, else the fallback static directory."""
    return FRONTEND_BUILD_DIR if (FRONTEND_BUILD_DIR / "index.html").exists() else STATIC_DIR


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    return response


@app.route("/")
def index():
    directory = frontend_entry_dir()
    return send_from_directory(str(directory), "index.html")


@app.route("/api/markets")
def search_markets():
    q = request.args.get("q", "")
    limit = int(request.args.get("limit", 20))

    gamma = get_gamma()
    all_markets = []
    for offset in range(0, 500, 100):
        page = gamma.get_markets(limit=100, offset=offset)
        all_markets.extend(page)
        if len(page) < 100:
            break

    if q:
        q_lower = q.lower()
        filtered = [m for m in all_markets if q_lower in m.question.lower()]
    else:
        filtered = all_markets

    filtered.sort(key=lambda m: m.volume, reverse=True)

    return jsonify(
        [
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
    )


@app.route("/api/orderbook/<token_id>")
def get_orderbook(token_id):
    try:
        ob = get_clob().get_orderbook(token_id)
        return jsonify(
            {
                "token_id": ob.token_id,
                "market_id": ob.market_id,
                "best_bid": ob.best_bid,
                "best_ask": ob.best_ask,
                "spread": ob.spread,
                "midpoint": ob.midpoint,
                "bids": [{"price": l.price, "size": l.size} for l in ob.bids[:15]],
                "asks": [{"price": l.price, "size": l.size} for l in ob.asks[:15]],
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/trade", methods=["POST"])
def place_trade():
    from polyclaw.trading.models import Side, TradeOrder, TradeOrderType

    req = request.json
    order = TradeOrder(
        token_id=req["token_id"],
        market_id=req.get("market_id", ""),
        market_question=req.get("question", ""),
        outcome=req.get("outcome", ""),
        side=Side(req["side"]),
        order_type=TradeOrderType.LIMIT if req.get("price") else TradeOrderType.MARKET,
        price=req.get("price"),
        size=req["size"],
    )
    result = get_trader().place_order(order)
    return jsonify(
        {
            "order_id": result.order_id,
            "status": result.status.value,
            "filled_price": result.filled_price,
            "filled_size": result.filled_size,
            "total_cost": result.total_cost,
            "message": result.message,
        }
    )


@app.route("/api/portfolio")
def get_portfolio():
    p = get_trader().get_portfolio()
    return jsonify(
        {
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
    )


@app.route("/api/reset", methods=["POST"])
def reset_portfolio():
    from polyclaw.config import settings

    get_trader().reset()
    return jsonify({"message": "Paper trading reset", "balance": settings.paper_starting_balance})


@app.route("/<path:full_path>")
def frontend_routes(full_path: str):
    """Serve the compiled React frontend for non-API routes."""
    if full_path.startswith("api/"):
        abort(404)

    directory = frontend_entry_dir()
    requested = directory / full_path

    if requested.is_file():
        return send_from_directory(str(directory), full_path)

    if "." in Path(full_path).name:
        abort(404)

    return send_from_directory(str(directory), "index.html")
