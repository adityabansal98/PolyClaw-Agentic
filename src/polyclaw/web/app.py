import logging
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_from_directory

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
FRONTEND_BUILD_DIR = STATIC_DIR / "app"

app = Flask(__name__, static_folder=str(STATIC_DIR))

# ── Register the /api/v1 Blueprint (Phase 3a) ────────────────────────────
from polyclaw.web.api_v1 import api_v1  # noqa: E402

app.register_blueprint(api_v1)

# Lazy singletons
_gamma = None
_clob = None
_trading_service = None
_dashboard_service = None


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


def get_trading_service():
    """Return the process-wide `TradingService`. Phase 2b single chokepoint: all order
    writes (dashboard + in-process agents + future HTTP callers) go through this."""
    global _trading_service
    if _trading_service is None:
        from polyclaw.config import settings
        from polyclaw.trading.paper_trader import make_dashboard_service

        _trading_service = make_dashboard_service(
            db_path=settings.paper_db_path,
            starting_balance=settings.paper_starting_balance,
            clob=get_clob(),
        )
    return _trading_service


def get_dashboard_service():
    global _dashboard_service
    if _dashboard_service is None:
        from polyclaw.web.dashboard_service import DashboardService

        _dashboard_service = DashboardService(
            gamma=get_gamma(),
            clob=get_clob(),
            trader=get_trading_service(),
        )
    return _dashboard_service


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


@app.route("/healthz")
def healthz():
    """Liveness probe — does NOT touch the database.

    For deeper checks (DB roundtrip, queue depth) see /api/v1/health (TODO).
    """
    return jsonify({"status": "ok"}), 200


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


@app.route("/api/dashboard/overview")
def dashboard_overview():
    try:
        return jsonify(get_dashboard_service().build_overview())
    except Exception as exc:
        logger.exception("Failed to build dashboard overview")
        return jsonify({"error": str(exc)}), 503


@app.route("/api/opportunities")
def list_opportunities():
    try:
        limit = int(request.args.get("limit", 36))
        return jsonify(get_dashboard_service().list_opportunities(limit=limit))
    except Exception as exc:
        logger.exception("Failed to list opportunities")
        return jsonify({"error": str(exc)}), 503


@app.route("/api/opportunities/<market_id>")
def opportunity_detail(market_id: str):
    try:
        detail = get_dashboard_service().get_opportunity_detail(market_id)
    except Exception as exc:
        logger.exception("Failed to load opportunity detail for %s", market_id)
        return jsonify({"error": str(exc)}), 503

    if detail is None:
        return jsonify({"error": f"Unknown opportunity {market_id}"}), 404

    return jsonify(detail)


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
                "updatedAt": ob.timestamp,
                "bids": [{"price": l.price, "size": l.size} for l in ob.bids[:15]],
                "asks": [{"price": l.price, "size": l.size} for l in ob.asks[:15]],
            }
        )
    except Exception as e:
        logger.exception("Failed to fetch orderbook for %s", token_id)
        return jsonify({"error": str(e)}), 503


@app.route("/api/trade", methods=["POST"])
def place_trade():
    return jsonify({"error": "Manual trading is disabled. Use the Agent Tools API (Phase 3)."}), 403


@app.route("/api/positions")
def get_positions():
    environment = request.args.get("environment", "paper")
    try:
        return jsonify(get_dashboard_service().list_positions(environment=environment))
    except Exception as exc:
        logger.exception("Failed to fetch positions for %s", environment)
        return jsonify({"error": str(exc)}), 503


@app.route("/api/portfolio")
def get_portfolio():
    environment = request.args.get("environment", "paper")
    try:
        return jsonify(get_dashboard_service().get_portfolio(environment=environment))
    except Exception as exc:
        logger.exception("Failed to fetch portfolio for %s", environment)
        return jsonify({"error": str(exc)}), 503


@app.route("/api/reset", methods=["POST"])
def reset_portfolio():
    """Reset the caller's paper-trading portfolio.

    Auth-required: scoped to the bearer-token's agent. Without auth this would
    let any caller wipe the dashboard agent's state — which used to be the
    behavior. Now: 401 if no token, scoped to g.agent_id otherwise.
    """
    from flask import g

    from polyclaw.config import settings
    from polyclaw.web.api_v1 import require_auth

    auth_err = require_auth()
    if auth_err:
        return auth_err

    agent_id = getattr(g, "agent_id", None)
    if not agent_id:
        return jsonify({"error": {"code": "auth.missing_agent", "message": "Could not resolve agent"}}), 401

    get_trading_service().reset(agent_id)
    get_dashboard_service().invalidate_paper_state()
    return jsonify({"message": "Paper trading reset", "balance": settings.paper_starting_balance})


@app.route("/api/strategy/opportunities")
def strategy_opportunities():
    try:
        from polyclaw.web.strategy_service import get_scored_opportunities

        picks = get_scored_opportunities()
        return jsonify({"items": picks, "count": len(picks)})
    except Exception as exc:
        logger.exception("Failed to get scored opportunities")
        return jsonify({"error": str(exc)}), 503


@app.route("/api/strategy/opportunities/<market_id>/bet", methods=["POST"])
def strategy_bet(market_id: str):
    return jsonify({"error": "Manual strategy bets are disabled. Use the Agent Tools API (Phase 3)."}), 403


@app.route("/api/backtest/strategies")
def list_backtest_strategies():
    """List available backtest strategies with their parameters."""
    from polyclaw.backtest.strategies import STRATEGY_REGISTRY

    strategies = []
    for name, cls in sorted(STRATEGY_REGISTRY.items()):
        instance = cls()
        params = {k: v for k, v in instance.__dict__.items() if not k.startswith("_")}
        strategies.append(
            {
                "name": name,
                "description": cls.__doc__.split("\n")[0] if cls.__doc__ else "",
                "params": params,
            }
        )
    return jsonify(strategies)


@app.route("/api/backtest", methods=["POST"])
def run_backtest():
    """[DEPRECATED] Synchronous backtest — superseded by /api/v1/backtest.

    The legacy route ran the full BacktestEngine inside a single Flask request
    with no auth and no quota. On Vercel this guaranteed a 60-second timeout
    on any non-trivial run, and it allowed unauthenticated callers to consume
    arbitrary CPU. Use the async queue instead:

        POST /api/v1/backtest         # enqueue
        GET  /api/v1/backtest/<id>    # poll
    """
    return jsonify({
        "error": {
            "code": "deprecated",
            "message": "POST /api/backtest is deprecated. Use POST /api/v1/backtest (async queue).",
            "docs": "https://github.com/adityabansal98/PolyClaw-Agentic#api-surface",
        }
    }), 410


# ── /api/arena/* — 410 Gone ────────────────────────────────────────────────
# The toy AgentArenaSimulation mechanic was deleted in Phase 2b (PLAN §7.2b).
# Every old arena route returns 410 Gone so any lingering cron/client surfaces
# a clear migration error instead of a 404. The full Agent Tools API lands in
# Phase 3 under /api/v1/*.


_ARENA_GONE_MESSAGE = (
    "The /api/arena/* surface was removed in Phase 2b. The toy coin arena is gone; "
    "agents now trade real shares through TradingService. See /api/v1/leaderboard "
    "for the new leaderboard (Phase 3 ships the full Agent Tools API)."
)


def _arena_gone(_path: str | None = None, **_kwargs):
    return jsonify({"error": "gone", "message": _ARENA_GONE_MESSAGE}), 410


for _arena_path in (
    "/api/arena/state",
    "/api/arena/tick",
    "/api/arena/register",
    "/api/arena/capabilities",
    "/api/arena/next-pick",
    "/api/arena/decision",
    "/api/arena/leaderboard",
    "/api/arena/markets",
):
    app.add_url_rule(
        _arena_path,
        endpoint=f"arena_gone_{_arena_path.replace('/', '_')}",
        view_func=_arena_gone,
        methods=["GET", "POST"],
    )


@app.route("/api/arena/market/<market_id>/bets", methods=["GET", "POST"])
def _arena_gone_market_bets(market_id: str):
    _ = market_id
    return _arena_gone()


@app.route("/api/arena/agent/<agent_name>/bets", methods=["GET", "POST"])
def _arena_gone_agent_bets(agent_name: str):
    _ = agent_name
    return _arena_gone()


# ── /api/v1/* routes are now in the api_v1 Blueprint (Phase 3a) ──────────
# leaderboard, backtest, portfolio, orders, quota, explain — all live in
# src/polyclaw/web/api_v1/*.py and are registered via app.register_blueprint above.


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
