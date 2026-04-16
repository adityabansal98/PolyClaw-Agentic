"""Phase 7 tests — approval workflow: request, approve, kill switch."""

from __future__ import annotations

from sqlalchemy import Engine

from polyclaw.agents.registry import AgentRegistry
from polyclaw.trading.clock import VirtualClock
from polyclaw.trading.market_data import ReplayMarketDataProvider
from polyclaw.trading.service import TradingService


def _setup(engine: Engine, monkeypatch):
    from polyclaw.web import app as web_app

    clock = VirtualClock(start_ms=1_700_000_000_000)
    svc = TradingService(engine=engine, clock=clock, market_data=ReplayMarketDataProvider())
    registry = AgentRegistry(engine, clock=clock)
    registry.create_agent("alice", name="Alice")
    token = registry.issue_key("alice")
    monkeypatch.setattr(web_app, "_trading_service", svc)
    return web_app.app.test_client(), {"Authorization": f"Bearer {token}"}, clock


def test_request_live(engine: Engine, monkeypatch):
    client, auth, _ = _setup(engine, monkeypatch)
    resp = client.post(
        "/api/v1/agents/alice/request-live",
        json={"message": "Ready for live trading"},
        headers=auth,
    )
    assert resp.status_code == 201
    assert resp.get_json()["status"] == "pending"


def test_request_live_duplicate_rejected(engine: Engine, monkeypatch):
    client, auth, _ = _setup(engine, monkeypatch)
    client.post("/api/v1/agents/alice/request-live", json={}, headers=auth)
    resp = client.post("/api/v1/agents/alice/request-live", json={}, headers=auth)
    assert resp.status_code == 409


def test_approve_live(engine: Engine, monkeypatch):
    client, auth, _ = _setup(engine, monkeypatch)
    client.post("/api/v1/agents/alice/request-live", json={}, headers=auth)

    resp = client.post(
        "/api/v1/agents/alice/approve-live",
        json={"confirmation_text": "I authorize alice for $1000", "max_live_usdc": 1000},
        headers=auth,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "approved"
    assert data["max_live_usdc"] == 1000


def test_approve_requires_confirmation(engine: Engine, monkeypatch):
    client, auth, _ = _setup(engine, monkeypatch)
    client.post("/api/v1/agents/alice/request-live", json={}, headers=auth)
    resp = client.post(
        "/api/v1/agents/alice/approve-live",
        json={"max_live_usdc": 1000},  # missing confirmation_text
        headers=auth,
    )
    assert resp.status_code == 400
    assert "confirmation" in resp.get_json()["error"]["code"]


def test_kill_switch_revokes_live(engine: Engine, monkeypatch):
    client, auth, _ = _setup(engine, monkeypatch)
    client.post("/api/v1/agents/alice/request-live", json={}, headers=auth)
    client.post(
        "/api/v1/agents/alice/approve-live",
        json={"confirmation_text": "I authorize", "max_live_usdc": 500},
        headers=auth,
    )
    resp = client.delete("/api/v1/agents/alice/live", headers=auth)
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "revoked"


def test_list_approvals(engine: Engine, monkeypatch):
    client, auth, _ = _setup(engine, monkeypatch)
    client.post("/api/v1/agents/alice/request-live", json={"message": "test"}, headers=auth)

    resp = client.get("/api/v1/approvals")
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    assert len(items) == 1
    assert items[0]["agent_id"] == "alice"
    assert items[0]["status"] == "pending"


def test_full_approval_lifecycle(engine: Engine, monkeypatch):
    """Request → approve → kill switch. Status transitions correctly."""
    client, auth, _ = _setup(engine, monkeypatch)

    # Request
    client.post("/api/v1/agents/alice/request-live", json={}, headers=auth)
    items = client.get("/api/v1/approvals").get_json()["items"]
    assert items[0]["status"] == "pending"

    # Approve
    client.post(
        "/api/v1/agents/alice/approve-live",
        json={"confirmation_text": "Go for it", "max_live_usdc": 2000},
        headers=auth,
    )
    items = client.get("/api/v1/approvals").get_json()["items"]
    assert items[0]["status"] == "approved"

    # Kill switch
    client.delete("/api/v1/agents/alice/live", headers=auth)
    items = client.get("/api/v1/approvals").get_json()["items"]
    assert items[0]["status"] == "revoked"
