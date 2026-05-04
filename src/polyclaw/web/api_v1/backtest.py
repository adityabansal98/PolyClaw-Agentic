"""Backtest enqueue + poll — moved from app.py inline route."""

from flask import g, jsonify, request

from polyclaw.web.api_v1 import api_v1, require_auth
from polyclaw.web.api_v1.errors import error_response
from polyclaw.workers.backtest_queue import BacktestQueue, QuotaExceeded


def _get_queue() -> BacktestQueue:
    from polyclaw.web.app import get_trading_service

    svc = get_trading_service()
    return BacktestQueue(svc.engine, clock=svc.clock)


@api_v1.route("/backtest", methods=["POST"])
def backtest_enqueue():
    """Enqueue an async backtest run. Auth required.

    Previously auth was optional and the route silently downgraded callers to
    the dashboard agent — which let any unauthenticated caller exhaust other
    agents' quotas via JSON body `agent_id`. Now: bearer required, agent_id
    always derived from the token (body `agent_id` ignored).
    """
    auth_err = require_auth()
    if auth_err:
        return auth_err

    agent_id = getattr(g, "agent_id", None)
    if not agent_id:
        return error_response("auth.missing_agent", "Could not resolve agent from token", status=401)

    payload = request.json or {}
    strategy = str(payload.get("strategy", "")).strip()
    markets = payload.get("markets") or []

    if not strategy:
        return error_response("bad_request.strategy", "strategy is required")
    if not isinstance(markets, list) or not markets:
        return error_response("bad_request.markets", "markets must be a non-empty list")

    queue = _get_queue()
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
        return error_response(exc.code, str(exc), status=429, details=exc.details)
    return jsonify({"backtest_id": run_id, "status": "queued"}), 202


@api_v1.route("/backtest/<run_id>")
def backtest_get(run_id: str):
    queue = _get_queue()
    row = queue.get(run_id)
    if row is None:
        return error_response("not_found", "Unknown backtest_id", 404)
    return jsonify(row)
