"""Post-V2 polish tests — safety circuit breakers, LiveTrader dispatch, equity curve endpoint."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, select, update

from polyclaw.agents.registry import AgentRegistry, AgentTier
from polyclaw.models.orderbook import OrderBook, OrderLevel
from polyclaw.storage.schema import agents, portfolio_snapshots
from polyclaw.trading.clock import VirtualClock
from polyclaw.trading.market_data import ReplayMarketDataProvider
from polyclaw.trading.models import Side, TradeOrder, TradeOrderType
from polyclaw.trading.risk_gate import RiskGateError
from polyclaw.trading.safety import SafetyConfig, SafetyMonitor
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


def _setup(engine: Engine, *, tier: AgentTier = AgentTier.HOSTED_INPROCESS):
    clock = VirtualClock(start_ms=1_700_000_000_000)
    provider = ReplayMarketDataProvider()
    provider.add("tok1", 0, _deep_book())
    svc = TradingService(engine=engine, clock=clock, market_data=provider)
    registry = AgentRegistry(engine, clock=clock)
    registry.create_agent("alice", name="Alice", starting_balance=10_000.0, tier=tier)
    return svc, clock, registry


# ── Safety: drawdown breaker ─────────────────────────────────────────────


def test_drawdown_breaker_pauses_agent(engine: Engine):
    svc, clock, registry = _setup(engine)

    # Flip to live_approved so safety monitor checks this agent
    with engine.begin() as conn:
        conn.execute(update(agents).where(agents.c.id == "alice").values(tier="live_approved"))

    # Insert a snapshot showing equity dropped to $6000 (40% DD from $10000)
    with engine.begin() as conn:
        conn.execute(
            portfolio_snapshots.insert().values(
                agent_id="alice",
                ts_ms=clock.now_ms(),
                cash=6000,
                position_value=0,
                total_equity=6000,
                realized_pnl=-4000,
                unrealized_pnl=0,
            )
        )

    config = SafetyConfig(max_drawdown_pct=30.0)  # 30% max DD → floor is $7000
    monitor = SafetyMonitor(engine, clock=clock, config=config)
    paused = monitor.check_all_agents()
    assert "alice" in paused

    # Agent is now paused
    with engine.connect() as conn:
        row = conn.execute(select(agents.c.status).where(agents.c.id == "alice")).first()
    assert row[0] == "paused"


def test_safety_skips_paper_agents(engine: Engine):
    """Safety monitor only checks live_approved agents, not paper."""
    svc, clock, _ = _setup(engine)

    # Insert bad snapshot but agent is NOT live_approved
    with engine.begin() as conn:
        conn.execute(
            portfolio_snapshots.insert().values(
                agent_id="alice",
                ts_ms=clock.now_ms(),
                cash=1,
                position_value=0,
                total_equity=1,
                realized_pnl=-9999,
                unrealized_pnl=0,
            )
        )

    monitor = SafetyMonitor(engine, clock=clock)
    paused = monitor.check_all_agents()
    assert paused == []  # not checked because not live_approved


# ── Paused agent rejected by RiskGate ─────────────────────────────────────


def test_paused_agent_cannot_trade(engine: Engine):
    svc, clock, registry = _setup(engine)

    with engine.begin() as conn:
        conn.execute(update(agents).where(agents.c.id == "alice").values(status="paused"))

    with pytest.raises(RiskGateError) as exc_info:
        svc.place_order(
            "alice",
            TradeOrder(
                token_id="tok1",
                market_id="mkt1",
                outcome="Yes",
                side=Side.BUY,
                order_type=TradeOrderType.MARKET,
                size=10,
            ),
        )
    assert exc_info.value.code == "risk_gate.agent_paused"


# ── Equity curve endpoint ─────────────────────────────────────────────────


def test_equity_curve_endpoint(engine: Engine, monkeypatch):
    from polyclaw.web import app as web_app

    svc, clock, registry = _setup(engine)
    monkeypatch.setattr(web_app, "_trading_service", svc)

    # Generate some snapshots by trading
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
    svc.place_order(
        "alice",
        TradeOrder(
            token_id="tok1",
            market_id="mkt1",
            outcome="Yes",
            side=Side.BUY,
            order_type=TradeOrderType.MARKET,
            size=25,
        ),
    )

    client = web_app.app.test_client()
    resp = client.get("/api/v1/agents/alice/equity-curve")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["agent_id"] == "alice"
    assert len(data["points"]) == 2
    # Points are ordered by time
    assert data["points"][0]["ts_ms"] <= data["points"][1]["ts_ms"]
    # Each point has the full shape
    p = data["points"][0]
    assert "cash" in p and "position_value" in p and "total_equity" in p
