"""Portfolio, positions, balance, trade history — agent-scoped reads."""

from flask import g, jsonify

from polyclaw.web.api_v1 import api_v1, require_auth


def _svc():
    from polyclaw.web.app import get_trading_service

    return get_trading_service()


@api_v1.route("/portfolio")
def get_portfolio():
    err = require_auth()
    if err:
        return err
    p = _svc().get_portfolio(g.agent_id)
    return jsonify(p.model_dump())


@api_v1.route("/positions")
def get_positions():
    err = require_auth()
    if err:
        return err
    positions = _svc().get_positions(g.agent_id)
    return jsonify([p.model_dump() for p in positions])


@api_v1.route("/balance")
def get_balance():
    err = require_auth()
    if err:
        return err
    return jsonify({"cash_balance": _svc().get_balance(g.agent_id)})


@api_v1.route("/trades")
def get_trade_history():
    err = require_auth()
    if err:
        return err
    return jsonify({"items": _svc().get_trade_history(g.agent_id)})


@api_v1.route("/agents/<agent_id>/equity-curve")
def agent_equity_curve(agent_id: str):
    """Public endpoint: return portfolio_snapshots time series for any agent.

    Used by the frontend's AgentDetailPage to render interactive equity curves
    without requiring a bearer token (the data is on the public leaderboard anyway).
    """
    from sqlalchemy import select

    from polyclaw.storage.schema import portfolio_snapshots

    svc = _svc()
    with svc.engine.connect() as conn:
        rows = (
            conn.execute(
                select(
                    portfolio_snapshots.c.ts_ms,
                    portfolio_snapshots.c.cash,
                    portfolio_snapshots.c.position_value,
                    portfolio_snapshots.c.total_equity,
                    portfolio_snapshots.c.realized_pnl,
                    portfolio_snapshots.c.unrealized_pnl,
                )
                .where(portfolio_snapshots.c.agent_id == agent_id)
                .order_by(portfolio_snapshots.c.ts_ms)
            )
            .mappings()
            .all()
        )
    return jsonify(
        {
            "agent_id": agent_id,
            "points": [
                {
                    "ts_ms": int(r["ts_ms"]),
                    "cash": float(r["cash"]),
                    "position_value": float(r["position_value"]),
                    "total_equity": float(r["total_equity"]),
                    "realized_pnl": float(r["realized_pnl"]),
                    "unrealized_pnl": float(r["unrealized_pnl"]),
                }
                for r in rows
            ],
        }
    )
