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
    from polyclaw.config import settings
    from polyclaw.storage.schema import DASHBOARD_AGENT_ID

    get_trading_service().reset(DASHBOARD_AGENT_ID)
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
    """Run a backtest with historical data."""
    from polyclaw.backtest.data_loader import DataLoader
    from polyclaw.backtest.engine import BacktestEngine
    from polyclaw.backtest.strategies import get_strategy

    req = request.json or {}
    strategy_name = req.get("strategy")
    markets_query = req.get("markets")

    if not strategy_name or not markets_query:
        return jsonify({"error": "strategy and markets are required"}), 400

    try:
        strategy = get_strategy(strategy_name)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    strategy.configure(req.get("params", {}))

    loader = DataLoader()
    market_data = loader.load_markets_by_query(
        markets_query,
        fidelity=req.get("fidelity", 60),
        limit=req.get("max_markets", 5),
    )

    if not market_data:
        return jsonify({"error": f"No markets found for: {markets_query!r}"}), 404

    engine = BacktestEngine(
        starting_cash=req.get("cash", 10_000.0),
        fee_bps=req.get("fee_bps", 0),
        slippage_pct=req.get("slippage_pct", 0.005),
    )
    result = engine.run(strategy, market_data)

    # Cap equity curve to 500 points for frontend performance
    curve = result.equity_curve
    if len(curve) > 500:
        step = len(curve) // 500
        curve = curve[::step] + [curve[-1]]

    return jsonify(
        {
            "backtest_id": result.backtest_id,
            "strategy_name": result.strategy_name,
            "starting_cash": result.starting_cash,
            "ending_cash": result.ending_cash,
            "ending_equity": result.ending_equity,
            "fee_bps": result.fee_bps,
            "fidelity": result.fidelity,
            "markets": result.markets,
            "strategy_params": result.strategy_params,
            "metrics": result.metrics.model_dump(),
            "trades": [t.model_dump() for t in result.trades],
            "equity_curve": [e.model_dump() for e in curve],
        }
    )


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


# ── /api/v1/leaderboard — Phase 2b scaffold ───────────────────────────────
# Minimum-viable leaderboard that reads from portfolio_snapshots. The full
# composite-metric version (Sharpe, drawdown, Calmar) arrives in Phase 4 with
# the Season engine. Phase 2b ships this just so the frontend AgentArenaPage
# has somewhere to point.


@app.route("/api/v1/leaderboard")
def api_v1_leaderboard():
    from sqlalchemy import desc, select

    from polyclaw.storage.schema import agents as agents_tbl
    from polyclaw.storage.schema import portfolio_snapshots

    svc = get_trading_service()
    engine = svc.engine

    items: list[dict] = []
    with engine.connect() as conn:
        agent_rows = conn.execute(select(agents_tbl)).mappings().all()
        for row in agent_rows:
            latest = (
                conn.execute(
                    select(
                        portfolio_snapshots.c.ts_ms,
                        portfolio_snapshots.c.cash,
                        portfolio_snapshots.c.position_value,
                        portfolio_snapshots.c.total_equity,
                        portfolio_snapshots.c.realized_pnl,
                    )
                    .where(portfolio_snapshots.c.agent_id == row["id"])
                    .order_by(desc(portfolio_snapshots.c.ts_ms))
                    .limit(1)
                )
                .mappings()
                .first()
            )
            starting = float(row["starting_balance"])
            equity = float(latest["total_equity"]) if latest else starting
            items.append(
                {
                    "agent_id": row["id"],
                    "name": row["name"],
                    "tier": row["tier"],
                    "total_equity": equity,
                    "return_pct": (equity - starting) / starting if starting > 0 else 0.0,
                    "last_update_ms": int(latest["ts_ms"]) if latest else None,
                }
            )
    items.sort(key=lambda x: x["return_pct"], reverse=True)
    return jsonify(
        {
            "items": items,
            "legacy_note": (
                "Seasons before 2026-05 ran on the legacy toy-coin arena mechanic and "
                "are not comparable to real paper-trading seasons. See "
                "docs/legacy-arena-history.json."
            ),
        }
    )


# ── /api/v1/backtest — Phase 2c async queue ───────────────────────────────
# Enqueue + poll routes. The worker loop (polyclaw.workers.backtest_worker) runs
# in a separate process (Railway in prod, docker-compose locally) and picks runs
# off via SKIP LOCKED. This route is just the producer + status peek.


def _get_backtest_queue():
    """Build a BacktestQueue bound to the process-wide TradingService engine."""
    from polyclaw.workers.backtest_queue import BacktestQueue

    svc = get_trading_service()
    return BacktestQueue(svc.engine, clock=svc.clock)


@app.route("/api/v1/backtest", methods=["POST"])
def api_v1_backtest_enqueue():
    from polyclaw.storage.schema import DASHBOARD_AGENT_ID
    from polyclaw.workers.backtest_queue import QuotaExceeded

    payload = request.json or {}
    # Phase 2c uses the dashboard agent as the default caller. Phase 3 replaces
    # this with the auth middleware's resolved bearer token → agent_id.
    agent_id = payload.get("agent_id", DASHBOARD_AGENT_ID)
    strategy = str(payload.get("strategy", "")).strip()
    markets = payload.get("markets") or []
    if not strategy:
        return jsonify({"error": {"code": "bad_request", "message": "strategy is required"}}), 400
    if not isinstance(markets, list) or not markets:
        return jsonify({"error": {"code": "bad_request", "message": "markets must be a non-empty list"}}), 400

    queue = _get_backtest_queue()
    try:
        run_id = queue.enqueue(
            agent_id=agent_id,
            strategy=strategy,
            params=payload.get("params") or {},
            markets=markets,
            fidelity=int(payload.get("fidelity", 60)),
            cash=float(payload.get("cash", 10_000.0)),
        )
    except QuotaExceeded as exc:
        return jsonify({"error": {"code": exc.code, "message": str(exc), "details": exc.details}}), 429
    return jsonify({"backtest_id": run_id, "status": "queued"}), 202


@app.route("/api/v1/backtest/<run_id>")
def api_v1_backtest_get(run_id: str):
    queue = _get_backtest_queue()
    row = queue.get(run_id)
    if row is None:
        return jsonify({"error": {"code": "not_found", "message": "unknown backtest_id"}}), 404
    return jsonify(row)


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
