"""Agent Tools API v1 — /api/v1/* Blueprint with auth + structured errors.

Phase 3a. Every route in this Blueprint:
- Injects a `request_id` UUID (available in `g.request_id`, returned as `X-Request-Id`)
- Resolves bearer tokens via `AgentRegistry.resolve_key` (routes that need auth)
- Returns errors through the structured envelope (`{error: {code, message, ...}}`)
- Catches `RiskGateError` and `QuotaExceeded` and maps them to 403/429 with the
  machine-readable `code` so agents can branch cleanly.

Auth is opt-in per route: read-only public routes (leaderboard, markets) skip auth.
Writes + portfolio reads require a valid bearer → `g.agent_id`.
"""

from __future__ import annotations

import logging
import uuid

from flask import Blueprint, g, request

from polyclaw.web.api_v1.errors import error_response

logger = logging.getLogger(__name__)

api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")


# ── Before-request: request_id injection ──────────────────────────────────


@api_v1.before_request
def _inject_request_id():
    g.request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())


@api_v1.after_request
def _echo_request_id(response):
    response.headers["X-Request-Id"] = getattr(g, "request_id", "")
    return response


# ── Auth helper ───────────────────────────────────────────────────────────


def require_auth():
    """Call at the top of any route that needs a bearer token. Sets `g.agent_id`
    on success; returns a structured 401 on failure."""
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        return error_response("auth.missing_token", "Authorization: Bearer <token> required", 401)

    token = auth.split(" ", 1)[1].strip()
    if not token:
        return error_response("auth.missing_token", "Bearer token is empty", 401)

    # Lazy import so the Blueprint can be imported without wiring the full app
    from polyclaw.web.app import get_trading_service

    svc = get_trading_service()
    from polyclaw.agents.registry import AgentRegistry

    registry = AgentRegistry(svc.engine, clock=svc.clock)
    agent_id = registry.resolve_key(token)
    if agent_id is None:
        return error_response("auth.invalid_token", "Unknown or revoked bearer token", 401)

    g.agent_id = agent_id
    return None


# ── Error handlers ────────────────────────────────────────────────────────


@api_v1.errorhandler(404)
def _handle_404(exc):
    return error_response("not_found", str(exc) or "Resource not found", 404)


@api_v1.errorhandler(Exception)
def _handle_unhandled(exc):
    logger.exception("Unhandled error in /api/v1: %s", exc)
    return error_response("internal", "Internal server error", 500)


# ── Register sub-modules ─────────────────────────────────────────────────
# Imported here so the routes get registered on the Blueprint.
# Each sub-module does `from polyclaw.web.api_v1 import api_v1` and decorates
# its routes with `@api_v1.route(...)`.

from polyclaw.web.api_v1 import backtest as _backtest  # noqa: F401, E402
from polyclaw.web.api_v1 import leaderboard as _leaderboard  # noqa: F401, E402
from polyclaw.web.api_v1 import orders as _orders  # noqa: F401, E402
from polyclaw.web.api_v1 import portfolio as _portfolio  # noqa: F401, E402
from polyclaw.web.api_v1 import quota as _quota  # noqa: F401, E402
