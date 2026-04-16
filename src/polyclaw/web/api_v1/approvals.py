"""Phase 7 — Human approval workflow for live trading.

Routes:
- POST /api/v1/agents/:id/request-live   — agent requests promotion to live tier
- POST /api/v1/agents/:id/approve-live   — human approves with signed confirmation
- DELETE /api/v1/agents/:id/live          — kill switch: revoke live, freeze positions
- GET /api/v1/approvals                   — list pending + resolved approval requests
"""

from __future__ import annotations

from flask import g, jsonify, request
from sqlalchemy import BigInteger, Column, Index, Integer, String, Table, select, update

from polyclaw.storage.db import ensure_schema
from polyclaw.storage.schema import agents, metadata
from polyclaw.web.api_v1 import api_v1, require_auth
from polyclaw.web.api_v1.errors import error_response


def _svc():
    from polyclaw.web.app import get_trading_service

    return get_trading_service()


# ── Schema addition: approval_requests table ──────────────────────────────

approval_requests = Table(
    "approval_requests",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("agent_id", String, nullable=False),
    Column("requested_at_ms", BigInteger, nullable=False),
    Column("requested_by", String, nullable=False),  # agent_id or human contact
    Column("message", String, server_default=""),
    # "pending" | "approved" | "rejected" | "revoked"
    Column("status", String, nullable=False, server_default="pending"),
    Column("reviewed_at_ms", BigInteger),
    Column("reviewed_by", String),
    Column("review_message", String),
    # Signed confirmation text (human typed "I authorize...")
    Column("confirmation_text", String),
    # Max USDC the agent is allowed to trade live
    Column("max_live_usdc", Integer),
    Index("idx_approval_requests_agent", "agent_id"),
    Index("idx_approval_requests_status", "status"),
)


@api_v1.route("/agents/<agent_id>/request-live", methods=["POST"])
def request_live(agent_id: str):
    """Agent or human requests promotion to live tier."""
    err = require_auth()
    if err:
        return err
    svc = _svc()
    ensure_schema(svc.engine)

    payload = request.json or {}
    message = str(payload.get("message", "")).strip()

    with svc.engine.begin() as conn:
        # Check agent exists
        agent = conn.execute(select(agents).where(agents.c.id == agent_id)).mappings().first()
        if agent is None:
            return error_response("not_found", f"Agent {agent_id} not found", 404)

        # Check no pending request already
        existing = conn.execute(
            select(approval_requests)
            .where(approval_requests.c.agent_id == agent_id)
            .where(approval_requests.c.status == "pending")
        ).first()
        if existing:
            return error_response("conflict", "Agent already has a pending live request", 409)

        conn.execute(
            approval_requests.insert().values(
                agent_id=agent_id,
                requested_at_ms=svc.clock.now_ms(),
                requested_by=g.agent_id,
                message=message,
                status="pending",
            )
        )
    return jsonify({"ok": True, "agent_id": agent_id, "status": "pending"}), 201


@api_v1.route("/agents/<agent_id>/approve-live", methods=["POST"])
def approve_live(agent_id: str):
    """Human approves an agent for live trading with signed confirmation."""
    err = require_auth()
    if err:
        return err
    svc = _svc()

    payload = request.json or {}
    confirmation = str(payload.get("confirmation_text", "")).strip()
    max_live_usdc = int(payload.get("max_live_usdc", 1000))

    if not confirmation:
        return error_response(
            "bad_request.confirmation",
            "confirmation_text is required (e.g. 'I authorize agent X to trade up to $Y')",
        )

    with svc.engine.begin() as conn:
        # Find pending request
        req_row = (
            conn.execute(
                select(approval_requests)
                .where(approval_requests.c.agent_id == agent_id)
                .where(approval_requests.c.status == "pending")
            )
            .mappings()
            .first()
        )
        if req_row is None:
            return error_response("not_found", "No pending live request for this agent", 404)

        now = svc.clock.now_ms()
        conn.execute(
            update(approval_requests)
            .where(approval_requests.c.id == req_row["id"])
            .values(
                status="approved",
                reviewed_at_ms=now,
                reviewed_by=g.agent_id,
                review_message="Approved via API",
                confirmation_text=confirmation,
                max_live_usdc=max_live_usdc,
            )
        )
        # Flip agent tier to indicate live approval (actual LiveTrader dispatch is Phase 7.2)
        conn.execute(update(agents).where(agents.c.id == agent_id).values(tier="live_approved"))

    return jsonify({"ok": True, "agent_id": agent_id, "status": "approved", "max_live_usdc": max_live_usdc})


@api_v1.route("/agents/<agent_id>/live", methods=["DELETE"])
def kill_switch(agent_id: str):
    """Kill switch: revoke live access, mark agent back to paper tier."""
    err = require_auth()
    if err:
        return err
    svc = _svc()

    with svc.engine.begin() as conn:
        # Revoke any approved requests
        conn.execute(
            update(approval_requests)
            .where(approval_requests.c.agent_id == agent_id)
            .where(approval_requests.c.status == "approved")
            .values(status="revoked", reviewed_at_ms=svc.clock.now_ms())
        )
        # Flip tier back
        conn.execute(update(agents).where(agents.c.id == agent_id).values(tier="external_http"))

    # Cancel all open orders for safety
    svc.portfolios.trader_for(agent_id).check_open_orders()

    return jsonify({"ok": True, "agent_id": agent_id, "status": "revoked"})


@api_v1.route("/approvals")
def list_approvals():
    """List all approval requests (pending + resolved)."""
    svc = _svc()
    ensure_schema(svc.engine)

    with svc.engine.connect() as conn:
        rows = (
            conn.execute(select(approval_requests).order_by(approval_requests.c.requested_at_ms.desc()))
            .mappings()
            .all()
        )

    return jsonify(
        {
            "items": [
                {
                    "id": r["id"],
                    "agent_id": r["agent_id"],
                    "status": r["status"],
                    "requested_at_ms": r["requested_at_ms"],
                    "requested_by": r["requested_by"],
                    "message": r["message"],
                    "reviewed_at_ms": r["reviewed_at_ms"],
                    "confirmation_text": r["confirmation_text"],
                    "max_live_usdc": r["max_live_usdc"],
                }
                for r in rows
            ]
        }
    )
