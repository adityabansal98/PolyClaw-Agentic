"""Phase 2c tests — BacktestQueue (enqueue + claim + quota), worker loop,
portfolio sampler, /api/v1/backtest routes.

Parametrized across SQLite + Postgres via the engine fixture. SKIP LOCKED
behavior is only meaningful on Postgres; the SQLite leg exercises the same
code path via the BEGIN IMMEDIATE fallback.
"""

from __future__ import annotations

import threading
import time

import pytest
from sqlalchemy import Engine, select

from polyclaw.agents.registry import AgentRegistry
from polyclaw.models.orderbook import OrderBook, OrderLevel
from polyclaw.storage.schema import backtest_runs, portfolio_snapshots
from polyclaw.trading.clock import VirtualClock
from polyclaw.trading.market_data import ReplayMarketDataProvider
from polyclaw.trading.models import OrderStatus, Side, TradeOrder, TradeOrderType
from polyclaw.trading.service import TradingService
from polyclaw.workers.backtest_queue import (
    DEFAULT_MAX_CONCURRENT,
    BacktestQueue,
    QuotaExceeded,
)
from polyclaw.workers.backtest_worker import BacktestWorker


def _seed_agent(engine: Engine, agent_id: str = "alice", *, clock: VirtualClock | None = None) -> None:
    registry = AgentRegistry(engine, clock=clock or VirtualClock(start_ms=1_700_000_000_000))
    registry.create_agent(agent_id, name=agent_id)


def _sample_markets(n: int = 2) -> list[dict]:
    return [
        {"token_id": f"tok{i}", "market_id": "mkt1", "question": f"Q{i}", "outcome": "Yes"} for i in range(n)
    ]


# ── Enqueue + get ────────────────────────────────────────────────────────


def test_enqueue_and_get(engine: Engine):
    clock = VirtualClock(start_ms=1_700_000_000_000)
    _seed_agent(engine, clock=clock)
    q = BacktestQueue(engine, clock=clock)

    run_id = q.enqueue(
        agent_id="alice",
        strategy="momentum",
        params={"window": 20},
        markets=_sample_markets(3),
        fidelity=60,
        cash=1_000.0,
    )
    row = q.get(run_id)
    assert row is not None
    assert row["status"] == "queued"
    assert row["agent_id"] == "alice"
    assert row["strategy"] == "momentum"


def test_get_unknown_returns_none(engine: Engine):
    q = BacktestQueue(engine)
    assert q.get("not-a-run-id") is None


# ── Claim ────────────────────────────────────────────────────────────────


def test_claim_one_atomically_flips_status(engine: Engine):
    clock = VirtualClock(start_ms=1_700_000_000_000)
    _seed_agent(engine, clock=clock)
    q = BacktestQueue(engine, clock=clock)

    run_id = q.enqueue(agent_id="alice", strategy="momentum", params={}, markets=_sample_markets(1))
    clock.advance(1_000)

    claim = q.claim_one()
    assert claim is not None
    assert claim.id == run_id
    assert claim.strategy == "momentum"

    row = q.get(run_id)
    assert row["status"] == "running"
    assert row["started_at_ms"] is not None


def test_claim_one_returns_none_when_empty(engine: Engine):
    q = BacktestQueue(engine)
    assert q.claim_one() is None


def test_claim_one_respects_fifo_order(engine: Engine):
    clock = VirtualClock(start_ms=1_700_000_000_000)
    _seed_agent(engine, clock=clock)
    # Bump concurrent limit so we can enqueue multiple at once.
    q = BacktestQueue(engine, clock=clock, max_concurrent=10)

    first = q.enqueue(agent_id="alice", strategy="momentum", params={}, markets=_sample_markets(1))
    clock.advance(1_000)
    q.enqueue(agent_id="alice", strategy="momentum", params={}, markets=_sample_markets(1))
    clock.advance(1_000)
    q.enqueue(agent_id="alice", strategy="momentum", params={}, markets=_sample_markets(1))

    claim = q.claim_one()
    assert claim is not None
    assert claim.id == first  # oldest enqueued_at_ms wins


def test_claim_skips_running_and_finished(engine: Engine):
    """Only `status='queued'` rows are claimable."""
    clock = VirtualClock(start_ms=1_700_000_000_000)
    _seed_agent(engine, clock=clock)
    q = BacktestQueue(engine, clock=clock)

    run_id = q.enqueue(agent_id="alice", strategy="momentum", params={}, markets=_sample_markets(1))
    q.claim_one()  # now status=running
    # Nothing else queued → next claim returns None.
    assert q.claim_one() is None

    q.mark_finished(run_id, {"metrics": {"total_return": 0.1}})
    assert q.claim_one() is None


# ── Quota enforcement ────────────────────────────────────────────────────


def test_quota_max_markets_per_run(engine: Engine):
    _seed_agent(engine)
    q = BacktestQueue(engine, max_markets_per_run=3)
    with pytest.raises(QuotaExceeded) as exc_info:
        q.enqueue(agent_id="alice", strategy="momentum", params={}, markets=_sample_markets(5))
    assert exc_info.value.code == "quota.backtest_markets_per_run"
    assert exc_info.value.details["limit"] == 3


def test_quota_max_concurrent(engine: Engine):
    clock = VirtualClock(start_ms=1_700_000_000_000)
    _seed_agent(engine, clock=clock)
    q = BacktestQueue(engine, clock=clock, max_concurrent=2)

    q.enqueue(agent_id="alice", strategy="momentum", params={}, markets=_sample_markets(1))
    q.enqueue(agent_id="alice", strategy="momentum", params={}, markets=_sample_markets(1))

    with pytest.raises(QuotaExceeded) as exc_info:
        q.enqueue(agent_id="alice", strategy="momentum", params={}, markets=_sample_markets(1))
    assert exc_info.value.code == "quota.backtest_concurrent"
    assert exc_info.value.details["limit"] == 2


def test_quota_hourly(engine: Engine):
    clock = VirtualClock(start_ms=1_700_000_000_000)
    _seed_agent(engine, clock=clock)
    q = BacktestQueue(engine, clock=clock, max_concurrent=100, max_per_hour=3)

    for _ in range(3):
        run_id = q.enqueue(agent_id="alice", strategy="momentum", params={}, markets=_sample_markets(1))
        q.mark_finished(run_id, {})  # free the concurrent slot but keep the row

    with pytest.raises(QuotaExceeded) as exc_info:
        q.enqueue(agent_id="alice", strategy="momentum", params={}, markets=_sample_markets(1))
    assert exc_info.value.code == "quota.backtest_hourly"

    # Advance the clock past the hour window — new enqueues accepted again.
    clock.advance(3_600_001)
    q.enqueue(agent_id="alice", strategy="momentum", params={}, markets=_sample_markets(1))


def test_quota_concurrent_default_is_two(engine: Engine):
    """PLAN-stated default is 2. Regression test against silent retuning."""
    assert DEFAULT_MAX_CONCURRENT == 2


# ── Worker: unknown strategy → mark_failed ───────────────────────────────


def test_worker_marks_unknown_strategy_failed(engine: Engine):
    clock = VirtualClock(start_ms=1_700_000_000_000)
    _seed_agent(engine, clock=clock)
    q = BacktestQueue(engine, clock=clock)
    run_id = q.enqueue(
        agent_id="alice", strategy="definitely_not_a_strategy", params={}, markets=_sample_markets(1)
    )

    worker = BacktestWorker(engine, clock=clock)
    claim = q.claim_one()
    assert claim is not None
    worker._run_one(claim)

    row = q.get(run_id)
    assert row["status"] == "failed"
    assert row["error"]["type"] == "unknown_strategy"


# ── Worker: no market data → mark_failed with specific type ──────────────


def test_worker_marks_no_market_data_failed(engine: Engine):
    """If `price_ticks` has nothing for the requested tokens, the worker fails
    the run cleanly rather than passing an empty timeline into the engine."""
    clock = VirtualClock(start_ms=1_700_000_000_000)
    _seed_agent(engine, clock=clock)
    q = BacktestQueue(engine, clock=clock)
    run_id = q.enqueue(
        agent_id="alice",
        strategy="momentum",  # real strategy this time
        params={},
        markets=_sample_markets(1),
    )

    worker = BacktestWorker(engine, clock=clock)
    claim = q.claim_one()
    assert claim is not None
    worker._run_one(claim)

    row = q.get(run_id)
    assert row["status"] == "failed"
    assert row["error"]["type"] == "no_market_data"


# ── Sampler loop writes snapshots for every active agent ─────────────────


def test_sampler_writes_portfolio_snapshots(engine: Engine):
    clock = VirtualClock(start_ms=1_700_000_000_000)
    registry = AgentRegistry(engine, clock=clock)
    registry.create_agent("alice", name="Alice", starting_balance=1_000.0)
    registry.create_agent("bob", name="Bob", starting_balance=500.0)

    worker = BacktestWorker(engine, clock=clock)
    worker._sample_all_agents()

    with engine.connect() as conn:
        rows = conn.execute(
            select(portfolio_snapshots.c.agent_id).order_by(portfolio_snapshots.c.agent_id)
        ).all()
    agent_ids = {r[0] for r in rows}
    assert agent_ids == {"alice", "bob"}


# ── End-to-end: enqueue via HTTP route, worker processes, GET returns status ─


def test_backtest_routes_enqueue_and_get(engine: Engine, monkeypatch):
    """POST /api/v1/backtest enqueues; GET returns the status. Exercises the
    Flask surface end-to-end (sans a real worker) against the test engine."""
    from polyclaw.web import app as web_app

    clock = VirtualClock(start_ms=1_700_000_000_000)
    _seed_agent(engine, clock=clock)
    svc = TradingService(engine=engine, clock=clock, market_data=ReplayMarketDataProvider())
    monkeypatch.setattr(web_app, "_trading_service", svc)

    client = web_app.app.test_client()
    resp = client.post(
        "/api/v1/backtest",
        json={
            "agent_id": "alice",
            "strategy": "momentum",
            "markets": _sample_markets(2),
            "cash": 1_000.0,
        },
    )
    assert resp.status_code == 202
    payload = resp.get_json()
    run_id = payload["backtest_id"]
    assert payload["status"] == "queued"

    resp = client.get(f"/api/v1/backtest/{run_id}")
    assert resp.status_code == 200
    row = resp.get_json()
    assert row["id"] == run_id
    assert row["status"] == "queued"


def test_backtest_route_returns_429_on_quota(engine: Engine, monkeypatch):
    from polyclaw.web import app as web_app

    clock = VirtualClock(start_ms=1_700_000_000_000)
    _seed_agent(engine, clock=clock)
    svc = TradingService(engine=engine, clock=clock, market_data=ReplayMarketDataProvider())
    monkeypatch.setattr(web_app, "_trading_service", svc)

    client = web_app.app.test_client()
    # Over the max_markets_per_run limit of 20
    resp = client.post(
        "/api/v1/backtest",
        json={
            "agent_id": "alice",
            "strategy": "momentum",
            "markets": _sample_markets(25),
        },
    )
    assert resp.status_code == 429
    error = resp.get_json()["error"]
    assert error["code"] == "quota.backtest_markets_per_run"


def test_backtest_route_unknown_id_returns_404(engine: Engine, monkeypatch):
    from polyclaw.web import app as web_app

    svc = TradingService(engine=engine, market_data=ReplayMarketDataProvider())
    monkeypatch.setattr(web_app, "_trading_service", svc)

    client = web_app.app.test_client()
    resp = client.get("/api/v1/backtest/not-a-real-id")
    assert resp.status_code == 404
