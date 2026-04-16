"""Structured error envelope — every non-2xx from /api/v1/* uses this shape.

Contract (from PLAN §7.3):
    {
        "error": {
            "code": "risk_gate.max_order_size",      # stable, machine-readable
            "message": "Order size 3000 exceeds ...", # human-readable
            "request_id": "abc-123",                  # echoed from X-Request-Id
            "docs_url": "/api/v1/docs/risk",          # optional
            "details": {"limit": 2000, "current": 3000}  # optional, code-specific
        }
    }

Every error-raising path in api_v1 builds its response through `error_response()`
so the contract is enforced in one place, not scattered across 20 route handlers.
"""

from __future__ import annotations

from typing import Any

from flask import g, jsonify


def error_response(
    code: str,
    message: str,
    status: int = 400,
    *,
    details: dict[str, Any] | None = None,
    docs_url: str | None = None,
):
    """Build a structured error JSON response.

    `code` is a stable dot-separated machine-readable string (e.g.
    `risk_gate.max_order_size`, `auth.invalid_token`, `quota.backtest_hourly`).
    Clients branch on `code`, not on `message`.
    """
    body: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": getattr(g, "request_id", "unknown"),
    }
    if docs_url is not None:
        body["docs_url"] = docs_url
    if details is not None:
        body["details"] = details
    return jsonify({"error": body}), status
