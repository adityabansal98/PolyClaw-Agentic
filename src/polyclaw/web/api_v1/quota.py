"""Quota self-reporting — agents can check headroom without hitting 429s blind."""

from flask import g, jsonify
from sqlalchemy import func, select

from polyclaw.storage.schema import backtest_runs
from polyclaw.trading.risk_gate import DEFAULT_LIMITS, TIER_LIMITS
from polyclaw.web.api_v1 import api_v1, require_auth
from polyclaw.workers.backtest_queue import (
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_MAX_MARKETS_PER_RUN,
    DEFAULT_MAX_PER_HOUR,
)


def _svc():
    from polyclaw.web.app import get_trading_service

    return get_trading_service()


@api_v1.route("/quota")
def get_quota():
    err = require_auth()
    if err:
        return err

    svc = _svc()

    from polyclaw.agents.registry import AgentRegistry

    registry = AgentRegistry(svc.engine, clock=svc.clock)
    record = registry.get(g.agent_id)
    tier = record.tier.value if record else "external_http"
    limits = TIER_LIMITS.get(tier, DEFAULT_LIMITS)

    now_ms = svc.clock.now_ms()
    one_hour_ago = now_ms - 3_600_000
    with svc.engine.connect() as conn:
        bt_concurrent = conn.execute(
            select(func.count())
            .select_from(backtest_runs)
            .where(backtest_runs.c.agent_id == g.agent_id)
            .where(backtest_runs.c.status.in_(["queued", "running"]))
        ).scalar_one()
        bt_hourly = conn.execute(
            select(func.count())
            .select_from(backtest_runs)
            .where(backtest_runs.c.agent_id == g.agent_id)
            .where(backtest_runs.c.enqueued_at_ms >= one_hour_ago)
        ).scalar_one()

    return jsonify(
        {
            "agent_id": g.agent_id,
            "tier": tier,
            "trading": {
                "max_order_size_usdc": limits.max_order_size_usdc,
                "max_position_size_usdc": limits.max_position_size_usdc,
            },
            "backtest": {
                "max_concurrent": DEFAULT_MAX_CONCURRENT,
                "concurrent_used": int(bt_concurrent),
                "max_per_hour": DEFAULT_MAX_PER_HOUR,
                "hourly_used": int(bt_hourly),
                "max_markets_per_run": DEFAULT_MAX_MARKETS_PER_RUN,
            },
        }
    )
