"""Season admin API + upgraded leaderboard with composite metrics."""

from __future__ import annotations

from flask import jsonify, request

from polyclaw.seasons.engine import SeasonEngine
from polyclaw.web.api_v1 import api_v1, require_auth
from polyclaw.web.api_v1.errors import error_response


def _engine():
    from polyclaw.web.app import get_trading_service

    svc = get_trading_service()
    return SeasonEngine(svc.engine, clock=svc.clock)


@api_v1.route("/seasons", methods=["GET"])
def list_seasons():
    status = request.args.get("status")
    items = _engine().list_seasons(status=status)
    return jsonify({"items": [_season_dict(s) for s in items]})


@api_v1.route("/seasons/<season_id>", methods=["GET"])
def get_season(season_id: str):
    s = _engine().get_season(season_id)
    if s is None:
        return error_response("not_found", f"Season {season_id} not found", 404)
    return jsonify(_season_dict(s))


@api_v1.route("/seasons", methods=["POST"])
def create_season():
    err = require_auth()
    if err:
        return err
    payload = request.json or {}
    name = str(payload.get("name", "")).strip()
    if not name:
        return error_response("bad_request.name", "name is required")
    try:
        season_id = _engine().create_season(
            name=name,
            starts_at_ms=int(payload["starts_at_ms"]),
            ends_at_ms=int(payload["ends_at_ms"]),
            starting_balance=float(payload.get("starting_balance", 10_000)),
            mode=str(payload.get("mode", "paper")),
            market_universe_filter=payload.get("market_universe_filter"),
        )
    except (KeyError, ValueError) as exc:
        return error_response("bad_request", str(exc))
    return jsonify({"season_id": season_id}), 201


@api_v1.route("/seasons/<season_id>/transition", methods=["POST"])
def transition_season(season_id: str):
    err = require_auth()
    if err:
        return err
    payload = request.json or {}
    to_status = str(payload.get("status", "")).strip()
    if not to_status:
        return error_response("bad_request.status", "status is required")
    try:
        s = _engine().transition(season_id, to_status)
    except ValueError as exc:
        return error_response("bad_request.transition", str(exc))
    return jsonify(_season_dict(s))


@api_v1.route("/seasons/<season_id>/finalize", methods=["POST"])
def finalize_season(season_id: str):
    err = require_auth()
    if err:
        return err
    try:
        entries = _engine().finalize_season(season_id)
    except ValueError as exc:
        return error_response("bad_request", str(exc))
    return jsonify({"items": [_entry_dict(e) for e in entries]})


@api_v1.route("/seasons/<season_id>/results", methods=["GET"])
def season_results(season_id: str):
    entries = _engine().compute_leaderboard(season_id)
    return jsonify({"season_id": season_id, "items": [_entry_dict(e) for e in entries]})


def _season_dict(s):
    return {
        "id": s.id,
        "name": s.name,
        "starts_at_ms": s.starts_at_ms,
        "ends_at_ms": s.ends_at_ms,
        "starting_balance": s.starting_balance,
        "mode": s.mode,
        "status": s.status,
        "registration_open": s.registration_open,
    }


def _entry_dict(e):
    return {
        "rank": e.rank,
        "agent_id": e.agent_id,
        "name": e.name,
        "tier": e.tier,
        "total_equity": round(e.total_equity, 2),
        "total_return": round(e.total_return, 4),
        "sharpe": round(e.sharpe, 2) if e.sharpe is not None else None,
        "max_drawdown": round(e.max_drawdown, 4),
        "calmar": round(e.calmar, 2) if e.calmar else None,
        "win_rate": round(e.win_rate, 4),
        "trade_count": e.trade_count,
    }
