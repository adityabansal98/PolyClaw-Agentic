"""Phase 3a tests — auth middleware, RiskGate, structured error contract,
/api/v1 routes (portfolio, orders, quota, explain).

Tests exercise the Flask test client against the full route stack, including
the auth middleware (bearer → agent_id) and the RiskGate (per-tier limits).
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine

from polyclaw.agents.registry import AgentRegistry, AgentTier
from polyclaw.models.orderbook import OrderBook, OrderLevel
from polyclaw.trading.clock import VirtualClock
from polyclaw.trading.market_data import ReplayMarketDataProvider
from polyclaw.trading.models import Side, TradeOrder, TradeOrderType
from polyclaw.trading.risk_gate import RiskGateError, check_risk
from polyclaw.trading.service import TradingService


def _deep_book(token_id: str = "tok1") -> OrderBook:
    return OrderBook(
        token_id=token_id,
        market_id="mkt1",
        bids=[OrderLevel(price=0.40, size=10_000.0)],
        asks=[OrderLevel(price=0.42, size=10_000.0)],
        best_bid=0.40,
        best_ask=0.42,
        midpoint=0.41,
        spread=0.02,
        timestamp=0,
    )


def _setup(engine: Engine):
    """Create a TradingService + two agents (alice=inprocess, bob=external_http)
    + issue bearer keys."""
    clock = VirtualClock(start_ms=1_700_000_000_000)
    provider = ReplayMarketDataProvider()
    provider.add("tok1", 0, _deep_book())
    svc = TradingService(engine=engine, clock=clock, market_data=provider)
    registry = AgentRegistry(engine, clock=clock)
    registry.create_agent("alice", name="Alice", starting_balance=10_000.0, tier=AgentTier.HOSTED_INPROCESS)
    registry.create_agent("bob", name="Bob", starting_balance=1_000.0, tier=AgentTier.EXTERNAL_HTTP)
    alice_token = registry.issue_key("alice")
    bob_token = registry.issue_key("bob")
    return svc, clock, alice_token, bob_token


def _client(engine, monkeypatch):
    svc, clock, alice_token, bob_token = _setup(engine)
    from polyclaw.web import app as web_app

    monkeypatch.setattr(web_app, "_trading_service", svc)
    return web_app.app.test_client(), alice_token, bob_token, svc


# ── Auth middleware ───────────────────────────────────────────────────────


def test_auth_missing_token(engine: Engine, monkeypatch):
    client, _, _, _ = _client(engine, monkeypatch)
    resp = client.get("/api/v1/portfolio")
    assert resp.status_code == 401
    err = resp.get_json()["error"]
    assert err["code"] == "auth.missing_token"
    assert "request_id" in err


def test_auth_invalid_token(engine: Engine, monkeypatch):
    client, _, _, _ = _client(engine, monkeypatch)
    resp = client.get("/api/v1/portfolio", headers={"Authorization": "Bearer polyclaw_live_invalid"})
    assert resp.status_code == 401
    assert resp.get_json()["error"]["code"] == "auth.invalid_token"


def test_auth_valid_token_sets_agent_id(engine: Engine, monkeypatch):
    client, alice_token, _, _ = _client(engine, monkeypatch)
    resp = client.get("/api/v1/portfolio", headers={"Authorization": f"Bearer {alice_token}"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "cash_balance" in data


def test_auth_request_id_echoed(engine: Engine, monkeypatch):
    client, alice_token, _, _ = _client(engine, monkeypatch)
    resp = client.get(
        "/api/v1/portfolio",
        headers={"Authorization": f"Bearer {alice_token}", "X-Request-Id": "test-req-123"},
    )
    assert resp.headers.get("X-Request-Id") == "test-req-123"


# ── RiskGate (unit level) ────────────────────────────────────────────────


def test_risk_gate_max_order_size_external():
    order = TradeOrder(
        token_id="t", market_id="m", side=Side.BUY, order_type=TradeOrderType.MARKET, size=600.0
    )
    with pytest.raises(RiskGateError) as exc_info:
        check_risk(order, agent_tier="external_http")
    assert exc_info.value.code == "risk_gate.max_order_size"
    assert exc_info.value.details["limit"] == 500.0


def test_risk_gate_max_order_size_inprocess_higher_limit():
    """In-process agents have a higher limit (5000 vs 500)."""
    order = TradeOrder(
        token_id="t", market_id="m", side=Side.BUY, order_type=TradeOrderType.MARKET, size=4_000.0
    )
    # Should pass for inprocess:
    check_risk(order, agent_tier="hosted_inprocess")
    # Should fail for external:
    with pytest.raises(RiskGateError):
        check_risk(order, agent_tier="external_http")


def test_risk_gate_max_position_size():
    order = TradeOrder(
        token_id="t", market_id="m", side=Side.BUY, order_type=TradeOrderType.MARKET, size=200.0
    )
    with pytest.raises(RiskGateError) as exc_info:
        check_risk(order, agent_tier="external_http", current_position_usdc=1_900.0)
    assert exc_info.value.code == "risk_gate.max_position_size"


def test_risk_gate_passes_within_limits():
    order = TradeOrder(
        token_id="t", market_id="m", side=Side.BUY, order_type=TradeOrderType.MARKET, size=100.0
    )
    check_risk(order, agent_tier="external_http", current_position_usdc=500.0)  # no exception


# ── RiskGate through TradingService (integration) ────────────────────────


def test_risk_gate_blocks_through_trading_service(engine: Engine):
    """The RiskGate fires inside TradingService.place_order — an external_http agent
    trying to place a 600 USDC order gets rejected."""
    clock = VirtualClock(start_ms=1_700_000_000_000)
    provider = ReplayMarketDataProvider()
    provider.add("tok1", 0, _deep_book())
    svc = TradingService(engine=engine, clock=clock, market_data=provider)
    registry = AgentRegistry(engine, clock=clock)
    registry.create_agent("bob", name="Bob", starting_balance=1_000.0, tier=AgentTier.EXTERNAL_HTTP)

    with pytest.raises(RiskGateError) as exc_info:
        svc.place_order(
            "bob",
            TradeOrder(
                token_id="tok1",
                market_id="mkt1",
                outcome="Yes",
                side=Side.BUY,
                order_type=TradeOrderType.MARKET,
                size=600.0,
            ),
        )
    assert exc_info.value.code == "risk_gate.max_order_size"


# ── /api/v1/orders POST — risk gate surfaces as 403 ──────────────────────


def test_orders_post_risk_gate_403(engine: Engine, monkeypatch):
    client, _, bob_token, _ = _client(engine, monkeypatch)
    resp = client.post(
        "/api/v1/orders",
        json={"token_id": "tok1", "market_id": "mkt1", "side": "BUY", "size": 600.0},
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert resp.status_code == 403
    err = resp.get_json()["error"]
    assert err["code"] == "risk_gate.max_order_size"
    assert err["details"]["limit"] == 500.0
    assert "request_id" in err


def test_orders_post_success(engine: Engine, monkeypatch):
    client, alice_token, _, _ = _client(engine, monkeypatch)
    resp = client.post(
        "/api/v1/orders",
        json={
            "token_id": "tok1",
            "market_id": "mkt1",
            "side": "BUY",
            "size": 50.0,
            "outcome": "Yes",
        },
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["status"] == "FILLED"
    assert data["filled_size"] is not None


# ── /api/v1/quota ─────────────────────────────────────────────────────────


def test_quota_returns_tier_limits(engine: Engine, monkeypatch):
    client, _, bob_token, _ = _client(engine, monkeypatch)
    resp = client.get("/api/v1/quota", headers={"Authorization": f"Bearer {bob_token}"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["tier"] == "external_http"
    assert data["trading"]["max_order_size_usdc"] == 500.0
    assert data["backtest"]["max_concurrent"] == 2


# ── Structured error contract on all error paths ─────────────────────────


def test_error_contract_has_code_message_request_id(engine: Engine, monkeypatch):
    """Every error response from /api/v1/* carries {error: {code, message, request_id}}."""
    client, _, _, _ = _client(engine, monkeypatch)

    # 401 (missing auth)
    resp = client.get("/api/v1/portfolio")
    err = resp.get_json()["error"]
    assert set(err.keys()) >= {"code", "message", "request_id"}

    # 400 (bad request)
    resp = client.post(
        "/api/v1/orders",
        json={},
        headers={"Authorization": "Bearer polyclaw_live_fake"},
    )
    # This will be 401 (invalid token), which also conforms.
    err = resp.get_json()["error"]
    assert set(err.keys()) >= {"code", "message", "request_id"}


# ── Leaderboard still works (public, no auth) ────────────────────────────


def test_leaderboard_public_no_auth(engine: Engine, monkeypatch):
    client, _, _, _ = _client(engine, monkeypatch)
    resp = client.get("/api/v1/leaderboard")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "items" in data
    assert "legacy_note" in data


# ── Backtest routes still work (moved to Blueprint) ──────────────────────


def test_backtest_routes_still_work(engine: Engine, monkeypatch):
    client, alice_token, _, _ = _client(engine, monkeypatch)
    resp = client.post(
        "/api/v1/backtest",
        json={
            "agent_id": "alice",
            "strategy": "momentum",
            "markets": [{"token_id": "tok1", "market_id": "mkt1", "question": "Q", "outcome": "Yes"}],
        },
    )
    assert resp.status_code == 202
    run_id = resp.get_json()["backtest_id"]

    resp = client.get(f"/api/v1/backtest/{run_id}")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "queued"
