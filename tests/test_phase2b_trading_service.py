"""Phase 2b tests — AgentRegistry, PortfolioManager, TradingService chokepoint,
and the scaffolded /api/v1/leaderboard route.

These exercise the premise that in-process agents and HTTP callers go through
the same `TradingService.place_order` path (premise P3 in PLAN.md). The risk
gate hook point is stubbed in Phase 2b; Phase 3 replaces it with real checks
and adds tests that exercise rejection codes.
"""

from __future__ import annotations

from sqlalchemy import Engine, select

from polyclaw.agents import AgentRegistry, AgentTier, PortfolioManager
from polyclaw.models.orderbook import OrderBook, OrderLevel
from polyclaw.storage.schema import agent_keys, agents, portfolio_snapshots
from polyclaw.trading.clock import VirtualClock
from polyclaw.trading.market_data import ReplayMarketDataProvider
from polyclaw.trading.models import OrderStatus, Side, TradeOrder, TradeOrderType
from polyclaw.trading.service import TradingService

# ── Fixtures ───────────────────────────────────────────────────────────────


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


def _make_service(engine: Engine) -> tuple[TradingService, VirtualClock, ReplayMarketDataProvider]:
    clock = VirtualClock(start_ms=1_700_000_000_000)
    provider = ReplayMarketDataProvider()
    provider.add("tok1", 0, _deep_book())
    svc = TradingService(engine=engine, clock=clock, market_data=provider)
    return svc, clock, provider


# ── AgentRegistry ─────────────────────────────────────────────────────────


def test_registry_create_and_get(engine: Engine):
    clock = VirtualClock(start_ms=1_700_000_000_000)
    registry = AgentRegistry(engine, clock=clock)
    rec = registry.create_agent("alice", name="Alice", starting_balance=1_000.0)
    assert rec.id == "alice"
    assert rec.tier == AgentTier.HOSTED_INPROCESS
    assert rec.starting_balance == 1_000.0

    fetched = registry.get("alice")
    assert fetched is not None and fetched.name == "Alice"

    # Idempotent: second create returns the existing record, doesn't raise
    again = registry.create_agent("alice", name="Alice")
    assert again.created_at == rec.created_at

    # paper_config.cash_balance was seeded
    with engine.connect() as conn:
        from polyclaw.storage.schema import paper_config

        row = conn.execute(
            select(paper_config.c.value)
            .where(paper_config.c.agent_id == "alice")
            .where(paper_config.c.key == "cash_balance")
        ).first()
    assert row is not None
    assert float(row[0]) == 1_000.0


def test_registry_bearer_key_lifecycle(engine: Engine):
    clock = VirtualClock(start_ms=1_700_000_000_000)
    registry = AgentRegistry(engine, clock=clock)
    registry.create_agent("alice", name="Alice")

    token = registry.issue_key("alice")
    assert token.startswith("polyclaw_live_")

    # Plaintext token is NOT stored — only the hash
    with engine.connect() as conn:
        rows = conn.execute(select(agent_keys)).mappings().all()
    assert len(rows) == 1
    assert rows[0]["key_hash"] != token
    assert len(rows[0]["key_hash"]) == 64  # sha256 hex

    # Resolve round-trips
    assert registry.resolve_key(token) == "alice"
    # last_used_at gets bumped
    with engine.connect() as conn:
        row = conn.execute(select(agent_keys.c.last_used_at)).first()
    assert row[0] == clock.now_ms()

    # Revoke
    assert registry.revoke_key(token) is True
    assert registry.resolve_key(token) is None
    # Double-revoke is a no-op
    assert registry.revoke_key(token) is False


def test_registry_unknown_key_returns_none(engine: Engine):
    registry = AgentRegistry(engine)
    assert registry.resolve_key("polyclaw_live_fake") is None


# ── PortfolioManager ──────────────────────────────────────────────────────


def test_portfolio_manager_caches_traders(engine: Engine):
    clock = VirtualClock(start_ms=1_700_000_000_000)
    provider = ReplayMarketDataProvider()
    provider.add("tok1", 0, _deep_book())
    registry = AgentRegistry(engine, clock=clock)
    registry.create_agent("alice", name="Alice")

    pm = PortfolioManager(engine=engine, clock=clock, market_data=provider)
    t1 = pm.trader_for("alice")
    t2 = pm.trader_for("alice")
    assert t1 is t2  # cached

    pm.forget("alice")
    t3 = pm.trader_for("alice")
    assert t3 is not t1


# ── TradingService as single chokepoint ───────────────────────────────────


def test_trading_service_place_order(engine: Engine):
    svc, clock, _ = _make_service(engine)
    registry = AgentRegistry(engine, clock=clock)
    registry.create_agent("alice", name="Alice", starting_balance=1_000.0)

    result = svc.place_order(
        "alice",
        TradeOrder(
            token_id="tok1",
            market_id="mkt1",
            outcome="Yes",
            side=Side.BUY,
            order_type=TradeOrderType.MARKET,
            size=50.0,
        ),
    )
    assert result.status == OrderStatus.FILLED
    assert svc.get_balance("alice") == 950.0

    # Read path also works through the service
    portfolio = svc.get_portfolio("alice")
    assert portfolio.cash_balance == 950.0
    assert len(portfolio.positions) == 1

    history = svc.get_trade_history("alice")
    assert len(history) == 1


def test_trading_service_isolates_agents(engine: Engine):
    """Two agents writing through the same service see independent balances."""
    svc, clock, _ = _make_service(engine)
    registry = AgentRegistry(engine, clock=clock)
    registry.create_agent("alice", name="Alice", starting_balance=1_000.0)
    registry.create_agent("bob", name="Bob", starting_balance=500.0)

    svc.place_order(
        "alice",
        TradeOrder(
            token_id="tok1",
            market_id="mkt1",
            outcome="Yes",
            side=Side.BUY,
            order_type=TradeOrderType.MARKET,
            size=100.0,
        ),
    )

    assert svc.get_balance("alice") == 900.0
    assert svc.get_balance("bob") == 500.0


def test_trading_service_risk_gate_hook_is_called(engine: Engine, monkeypatch):
    """The RiskGate hook point fires on every place_order. Phase 3 replaces its
    body; Phase 2b just verifies the wiring exists so Phase 3 can monkeypatch."""
    svc, clock, _ = _make_service(engine)
    registry = AgentRegistry(engine, clock=clock)
    registry.create_agent("alice", name="Alice", starting_balance=1_000.0)

    calls: list[tuple[str, str]] = []
    original = svc._check_risk

    def spy(agent_id, order):
        calls.append((agent_id, order.side.value))
        return original(agent_id, order)

    monkeypatch.setattr(svc, "_check_risk", spy)

    svc.place_order(
        "alice",
        TradeOrder(
            token_id="tok1",
            market_id="mkt1",
            outcome="Yes",
            side=Side.BUY,
            order_type=TradeOrderType.MARKET,
            size=25.0,
        ),
    )

    assert calls == [("alice", "BUY")]


# ── Phase 2b scaffold: /api/v1/leaderboard ────────────────────────────────


def test_leaderboard_endpoint_reads_portfolio_snapshots(engine: Engine, monkeypatch):
    """The leaderboard endpoint returns one row per registered agent with the
    latest portfolio_snapshots entry and a legacy_note pointing to the
    legacy-arena-history.json file."""
    from polyclaw.web import app as web_app

    clock = VirtualClock(start_ms=1_700_000_000_000)
    provider = ReplayMarketDataProvider()
    provider.add("tok1", 0, _deep_book())
    registry = AgentRegistry(engine, clock=clock)
    registry.create_agent("alice", name="Alice", starting_balance=1_000.0)
    registry.create_agent("bob", name="Bob", starting_balance=500.0)

    svc = TradingService(engine=engine, clock=clock, market_data=provider)
    # Alice trades; bob doesn't. Both should appear on the board.
    svc.place_order(
        "alice",
        TradeOrder(
            token_id="tok1",
            market_id="mkt1",
            outcome="Yes",
            side=Side.BUY,
            order_type=TradeOrderType.MARKET,
            size=100.0,
        ),
    )

    # Inject our test service into the Flask app
    monkeypatch.setattr(web_app, "_trading_service", svc)

    client = web_app.app.test_client()
    response = client.get("/api/v1/leaderboard")
    assert response.status_code == 200
    payload = response.get_json()
    assert "legacy_note" in payload
    assert "legacy" in payload["legacy_note"].lower()

    items = {row["agent_id"]: row for row in payload["items"]}
    assert set(items.keys()) == {"alice", "bob"}
    # Alice has a snapshot row after her trade → last_update_ms is not None.
    assert items["alice"]["last_update_ms"] is not None
    # Bob never traded → no snapshot → total_equity falls back to starting balance.
    assert items["bob"]["total_equity"] == 500.0
    assert items["bob"]["return_pct"] == 0.0


def test_arena_routes_return_410(engine: Engine):
    """Every old /api/arena/* route returns 410 Gone."""
    from polyclaw.web import app as web_app

    client = web_app.app.test_client()
    for path in (
        "/api/arena/state",
        "/api/arena/capabilities",
        "/api/arena/leaderboard",
        "/api/arena/markets",
    ):
        response = client.get(path)
        assert response.status_code == 410, f"{path} returned {response.status_code}"
        payload = response.get_json()
        assert payload["error"] == "gone"


# ── portfolio_snapshots is written on every trade through the service ────


def test_portfolio_snapshots_written_through_service(engine: Engine):
    svc, clock, _ = _make_service(engine)
    registry = AgentRegistry(engine, clock=clock)
    registry.create_agent("alice", name="Alice", starting_balance=1_000.0)

    svc.place_order(
        "alice",
        TradeOrder(
            token_id="tok1",
            market_id="mkt1",
            outcome="Yes",
            side=Side.BUY,
            order_type=TradeOrderType.MARKET,
            size=50.0,
        ),
    )
    clock.advance(1_000)
    svc.place_order(
        "alice",
        TradeOrder(
            token_id="tok1",
            market_id="mkt1",
            outcome="Yes",
            side=Side.BUY,
            order_type=TradeOrderType.MARKET,
            size=25.0,
        ),
    )

    with engine.connect() as conn:
        rows = (
            conn.execute(
                select(portfolio_snapshots)
                .where(portfolio_snapshots.c.agent_id == "alice")
                .order_by(portfolio_snapshots.c.ts_ms)
            )
            .mappings()
            .all()
        )
    # One row per trade (sampler writes inside the tx)
    assert len(rows) == 2
    # Cash monotonically decreases as alice spends
    assert rows[0]["cash"] > rows[1]["cash"]


# ── agents table sanity ───────────────────────────────────────────────────


def test_agents_table_populated_on_create(engine: Engine):
    registry = AgentRegistry(engine)
    registry.create_agent("alice", name="Alice", tier=AgentTier.EXTERNAL_HTTP)

    with engine.connect() as conn:
        row = conn.execute(select(agents).where(agents.c.id == "alice")).mappings().first()
    assert row is not None
    assert row["tier"] == AgentTier.EXTERNAL_HTTP.value
    assert row["status"] == "active"
