"""Phase 4 tests — season lifecycle, composite leaderboard metrics, auto-tick."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, select

from polyclaw.agents.registry import AgentRegistry
from polyclaw.models.orderbook import OrderBook, OrderLevel
from polyclaw.seasons.engine import SeasonEngine
from polyclaw.storage.schema import season_results
from polyclaw.trading.clock import VirtualClock
from polyclaw.trading.market_data import ReplayMarketDataProvider
from polyclaw.trading.models import Side, TradeOrder, TradeOrderType
from polyclaw.trading.service import TradingService


def _deep_book():
    return OrderBook(
        token_id="tok1",
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
    clock = VirtualClock(start_ms=1_700_000_000_000)
    provider = ReplayMarketDataProvider()
    provider.add("tok1", 0, _deep_book())
    registry = AgentRegistry(engine, clock=clock)
    svc = TradingService(engine=engine, clock=clock, market_data=provider)
    se = SeasonEngine(engine, clock=clock)
    return clock, registry, svc, se


# ── Season lifecycle ──────────────────────────────────────────────────────


def test_season_lifecycle(engine: Engine):
    clock, _, _, se = _setup(engine)
    sid = se.create_season(
        name="Test Season", starts_at_ms=clock.now_ms() + 1000, ends_at_ms=clock.now_ms() + 10000
    )
    s = se.get_season(sid)
    assert s is not None and s.status == "draft"

    se.transition(sid, "open_registration")
    assert se.get_season(sid).status == "open_registration"

    se.transition(sid, "running")
    s = se.get_season(sid)
    assert s.status == "running"
    assert not s.registration_open  # closed on running


def test_invalid_transition_raises(engine: Engine):
    _, _, _, se = _setup(engine)
    sid = se.create_season(name="T", starts_at_ms=0, ends_at_ms=1)
    with pytest.raises(ValueError, match="Cannot transition"):
        se.transition(sid, "finalized")  # draft → finalized not valid


def test_start_season_convenience(engine: Engine):
    _, _, _, se = _setup(engine)
    sid = se.create_season(name="T", starts_at_ms=0, ends_at_ms=1)
    s = se.start_season(sid)
    assert s.status == "running"


# ── Composite leaderboard ────────────────────────────────────────────────


def test_composite_leaderboard_with_trades(engine: Engine):
    """Two agents trade, leaderboard ranks them by composite metric."""
    clock, registry, svc, se = _setup(engine)
    registry.create_agent("alice", name="Alice", starting_balance=1000)
    registry.create_agent("bob", name="Bob", starting_balance=1000)

    # Alice buys aggressively, bob doesn't trade
    svc.place_order(
        "alice",
        TradeOrder(
            token_id="tok1",
            market_id="mkt1",
            outcome="Yes",
            side=Side.BUY,
            order_type=TradeOrderType.MARKET,
            size=200,
        ),
    )
    clock.advance(60_000)
    svc.place_order(
        "alice",
        TradeOrder(
            token_id="tok1",
            market_id="mkt1",
            outcome="Yes",
            side=Side.BUY,
            order_type=TradeOrderType.MARKET,
            size=100,
        ),
    )

    entries = se.compute_leaderboard()
    assert len(entries) == 2
    # Alice traded, bob didn't — Alice should have non-zero trade count
    alice_entry = next(e for e in entries if e.agent_id == "alice")
    bob_entry = next(e for e in entries if e.agent_id == "bob")
    assert alice_entry.trade_count == 2
    assert bob_entry.trade_count == 0
    # Both have assigned ranks
    assert alice_entry.rank >= 1
    assert bob_entry.rank >= 1


def test_composite_metrics_computed(engine: Engine):
    """Sharpe, max DD, calmar are computed from portfolio snapshots."""
    clock, registry, svc, se = _setup(engine)
    registry.create_agent("alice", name="Alice", starting_balance=1000)

    # Several trades to generate snapshots
    for _ in range(5):
        svc.place_order(
            "alice",
            TradeOrder(
                token_id="tok1",
                market_id="mkt1",
                outcome="Yes",
                side=Side.BUY,
                order_type=TradeOrderType.MARKET,
                size=50,
            ),
        )
        clock.advance(60_000)

    entries = se.compute_leaderboard()
    alice = next(e for e in entries if e.agent_id == "alice")
    assert alice.sharpe is not None  # enough snapshots to compute
    assert alice.max_drawdown >= 0.0
    assert alice.trade_count == 5  # all trades counted


# ── Season finalization ───────────────────────────────────────────────────


def test_finalize_writes_season_results(engine: Engine):
    clock, registry, svc, se = _setup(engine)
    sid = se.create_season(name="Playoff", starts_at_ms=0, ends_at_ms=clock.now_ms() + 5000)
    se.start_season(sid)

    registry.create_agent("alice", name="Alice", starting_balance=1000)
    svc.place_order(
        "alice",
        TradeOrder(
            token_id="tok1",
            market_id="mkt1",
            outcome="Yes",
            side=Side.BUY,
            order_type=TradeOrderType.MARKET,
            size=100,
        ),
    )

    entries = se.finalize_season(sid)
    assert se.get_season(sid).status == "finalized"
    assert len(entries) >= 1

    # season_results rows written
    with engine.connect() as conn:
        rows = conn.execute(select(season_results).where(season_results.c.season_id == sid)).all()
    assert len(rows) >= 1


def test_finalize_idempotent(engine: Engine):
    """Finalizing twice doesn't duplicate season_results rows."""
    clock, registry, svc, se = _setup(engine)
    sid = se.create_season(name="T", starts_at_ms=0, ends_at_ms=1)
    se.start_season(sid)
    registry.create_agent("alice", name="Alice", starting_balance=1000)

    se.finalize_season(sid)
    # Can't finalize again (already finalized, no valid transition)
    with pytest.raises(ValueError):
        se.finalize_season(sid)


# ── Auto-tick ─────────────────────────────────────────────────────────────


def test_auto_tick_starts_season(engine: Engine):
    clock, _, _, se = _setup(engine)
    sid = se.create_season(name="Auto", starts_at_ms=clock.now_ms() + 100, ends_at_ms=clock.now_ms() + 10000)
    se.transition(sid, "open_registration")

    # Before start time — tick does nothing
    se.tick()
    assert se.get_season(sid).status == "open_registration"

    # After start time — tick auto-transitions to running
    clock.advance(200)
    se.tick()
    assert se.get_season(sid).status == "running"


def test_auto_tick_finalizes_season(engine: Engine):
    clock, registry, _, se = _setup(engine)
    registry.create_agent("alice", name="Alice")
    sid = se.create_season(name="Auto", starts_at_ms=clock.now_ms(), ends_at_ms=clock.now_ms() + 100)
    se.start_season(sid)

    # Before end — still running
    se.tick()
    assert se.get_season(sid).status == "running"

    # After end — auto-finalized
    clock.advance(200)
    se.tick()
    assert se.get_season(sid).status == "finalized"


# ── Season API routes ─────────────────────────────────────────────────────


def test_seasons_crud_via_api(engine: Engine, monkeypatch):
    from polyclaw.web import app as web_app

    clock, registry, svc, _ = _setup(engine)
    registry.create_agent("alice", name="Alice")
    token = registry.issue_key("alice")
    monkeypatch.setattr(web_app, "_trading_service", svc)
    client = web_app.app.test_client()
    auth = {"Authorization": f"Bearer {token}"}

    # Create
    resp = client.post(
        "/api/v1/seasons",
        json={
            "name": "API Season",
            "starts_at_ms": 1000,
            "ends_at_ms": 9999,
        },
        headers=auth,
    )
    assert resp.status_code == 201
    sid = resp.get_json()["season_id"]

    # List
    resp = client.get("/api/v1/seasons")
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    assert any(s["id"] == sid for s in items)

    # Get
    resp = client.get(f"/api/v1/seasons/{sid}")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "draft"

    # Transition
    resp = client.post(
        f"/api/v1/seasons/{sid}/transition", json={"status": "open_registration"}, headers=auth
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "open_registration"
