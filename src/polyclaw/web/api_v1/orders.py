"""Order placement, cancellation, and order explain (audit trail read)."""

from __future__ import annotations

import json

from flask import g, jsonify, request
from sqlalchemy import select

from polyclaw.storage.schema import audit_log, orderbook_snapshots, paper_trades
from polyclaw.trading.models import Side, TradeOrder, TradeOrderType
from polyclaw.trading.risk_gate import RiskGateError
from polyclaw.web.api_v1 import api_v1, require_auth
from polyclaw.web.api_v1.errors import error_response


def _svc():
    from polyclaw.web.app import get_trading_service

    return get_trading_service()


@api_v1.route("/orders", methods=["POST"])
def place_order():
    err = require_auth()
    if err:
        return err

    svc = _svc()
    payload = request.json or {}

    token_id = str(payload.get("token_id", "")).strip()
    market_id = str(payload.get("market_id", "")).strip()
    side = str(payload.get("side", "")).upper()
    order_type = str(payload.get("order_type", "MARKET")).upper()
    size = payload.get("size")
    price = payload.get("price")

    if not token_id:
        return error_response("bad_request.token_id", "token_id is required")
    if not market_id:
        return error_response("bad_request.market_id", "market_id is required")
    if side not in ("BUY", "SELL"):
        return error_response("bad_request.side", "side must be BUY or SELL")
    if size is None or float(size) <= 0:
        return error_response("bad_request.size", "size must be > 0")
    if order_type == "LIMIT" and price is None:
        return error_response("bad_request.price", "price is required for LIMIT orders")

    order = TradeOrder(
        token_id=token_id,
        market_id=market_id,
        market_question=str(payload.get("market_question", "")),
        outcome=str(payload.get("outcome", "")),
        side=Side(side),
        order_type=TradeOrderType(order_type),
        price=float(price) if price is not None else None,
        size=float(size),
    )

    try:
        result = svc.place_order(g.agent_id, order, request_id=g.request_id)
    except RiskGateError as exc:
        return error_response(
            exc.code,
            str(exc),
            status=403,
            details=exc.details,
            docs_url="/api/v1/docs/risk",
        )

    return jsonify(result.model_dump()), 201


@api_v1.route("/orders/<order_id>", methods=["DELETE"])
def cancel_order(order_id: str):
    err = require_auth()
    if err:
        return err
    cancelled = _svc().cancel_order(g.agent_id, order_id)
    if not cancelled:
        return error_response("not_found", f"Order {order_id} not found or already filled", 404)
    return jsonify({"ok": True, "order_id": order_id})


@api_v1.route("/orders/<order_id>/explain")
def explain_order(order_id: str):
    """Return the audit trail for a single order: the orderbook snapshot, the fill,
    the RiskGate decision. Pulled forward from Phase 5 per eng review."""
    err = require_auth()
    if err:
        return err

    svc = _svc()
    engine = svc.engine

    with engine.connect() as conn:
        trade_row = (
            conn.execute(
                select(paper_trades)
                .where(paper_trades.c.id == order_id)
                .where(paper_trades.c.agent_id == g.agent_id)
            )
            .mappings()
            .first()
        )
        if trade_row is None:
            return error_response("not_found", f"Trade {order_id} not found for your agent", 404)

        audit_row = (
            conn.execute(
                select(audit_log)
                .where(audit_log.c.agent_id == g.agent_id)
                .where(audit_log.c.ts_ms == trade_row["timestamp"])
                .limit(1)
            )
            .mappings()
            .first()
        )

        snapshot = None
        if audit_row and audit_row["orderbook_snapshot_id"]:
            snap_row = (
                conn.execute(
                    select(orderbook_snapshots).where(
                        orderbook_snapshots.c.id == audit_row["orderbook_snapshot_id"]
                    )
                )
                .mappings()
                .first()
            )
            if snap_row:
                snapshot = json.loads(snap_row["snapshot_json"])

    return jsonify(
        {
            "trade": dict(trade_row),
            "audit": dict(audit_row) if audit_row else None,
            "orderbook_snapshot": snapshot,
        }
    )
