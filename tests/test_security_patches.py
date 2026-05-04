"""Security regression tests for the patches applied in HW9 prep.

These tests guard the 3 critical fixes from the autoplan review:
1. /api/reset must require auth (was wide open)
2. /api/v1/backtest must require auth (was bypassable via JSON body agent_id)
3. /api/backtest legacy sync route must be 410 Gone (was a Vercel timeout target)

Run against production:
    pytest tests/test_security_patches.py -v -m network
"""

import json
import urllib.request
import urllib.error

import pytest

PRODUCTION_URL = "https://poly-claw-agentic.vercel.app"


def _post(url: str, payload: dict) -> tuple[int, dict]:
    """POST JSON, return (status, body). Catches HTTPError to inspect non-2xx."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "polyclaw-test"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        body = {}
        try:
            body = json.loads(e.read() or b"{}")
        except Exception:
            pass
        return e.code, body


@pytest.mark.network
def test_api_reset_requires_auth():
    """[critical] /api/reset must reject unauthenticated calls.

    Was: wide open, wiped __dashboard__'s entire portfolio without any auth.
    Combined with `Access-Control-Allow-Origin: *` this was a CSRF gift.
    """
    status, body = _post(f"{PRODUCTION_URL}/api/reset", {})
    assert status == 401, (
        f"Expected 401 from /api/reset without auth, got {status}. "
        f"Auth bypass may have been reintroduced. Response: {body}"
    )


@pytest.mark.network
def test_api_v1_backtest_requires_auth():
    """[critical] /api/v1/backtest must reject unauthenticated calls.

    Was: auth was optional. Unauthenticated callers fell back to __dashboard__,
    then could provide any agent_id in the JSON body and exhaust that agent's
    hourly quota. Now: auth required, agent_id derived from token only.
    """
    status, body = _post(
        f"{PRODUCTION_URL}/api/v1/backtest",
        {"strategy": "momentum", "markets": ["test"], "agent_id": "victim"},
    )
    assert status == 401, (
        f"Expected 401 from /api/v1/backtest without auth, got {status}. "
        f"Auth bypass may have been reintroduced. Response: {body}"
    )


@pytest.mark.network
def test_legacy_sync_backtest_returns_410():
    """[critical] /api/backtest legacy sync route must be 410 Gone.

    Was: ran the full BacktestEngine inside a Vercel function with no auth, no
    quota — guaranteed 60s timeout on any non-trivial run.
    """
    status, body = _post(
        f"{PRODUCTION_URL}/api/backtest",
        {"strategy": "momentum", "markets": "NBA"},
    )
    assert status == 410, (
        f"Expected 410 from legacy /api/backtest, got {status}. "
        f"Sync backtest route may have been reintroduced. Response: {body}"
    )


@pytest.mark.network
def test_healthz_responds():
    """Liveness probe must work."""
    req = urllib.request.Request(
        f"{PRODUCTION_URL}/healthz",
        headers={"User-Agent": "polyclaw-test"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        assert r.status == 200
        body = json.loads(r.read())
        assert body == {"status": "ok"}
