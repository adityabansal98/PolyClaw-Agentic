"""Leaderboard — public, no auth. Moved from app.py inline route."""

from flask import jsonify
from sqlalchemy import desc, select

from polyclaw.storage.schema import agents as agents_tbl
from polyclaw.storage.schema import portfolio_snapshots
from polyclaw.web.api_v1 import api_v1


def _svc():
    from polyclaw.web.app import get_trading_service

    return get_trading_service()


@api_v1.route("/leaderboard")
def leaderboard():
    svc = _svc()
    engine = svc.engine

    items: list[dict] = []
    with engine.connect() as conn:
        agent_rows = conn.execute(select(agents_tbl)).mappings().all()
        for row in agent_rows:
            latest = (
                conn.execute(
                    select(
                        portfolio_snapshots.c.ts_ms,
                        portfolio_snapshots.c.cash,
                        portfolio_snapshots.c.position_value,
                        portfolio_snapshots.c.total_equity,
                        portfolio_snapshots.c.realized_pnl,
                    )
                    .where(portfolio_snapshots.c.agent_id == row["id"])
                    .order_by(desc(portfolio_snapshots.c.ts_ms))
                    .limit(1)
                )
                .mappings()
                .first()
            )
            starting = float(row["starting_balance"])
            equity = float(latest["total_equity"]) if latest else starting
            items.append(
                {
                    "agent_id": row["id"],
                    "name": row["name"],
                    "tier": row["tier"],
                    "total_equity": equity,
                    "return_pct": (equity - starting) / starting if starting > 0 else 0.0,
                    "last_update_ms": int(latest["ts_ms"]) if latest else None,
                }
            )
    items.sort(key=lambda x: x["return_pct"], reverse=True)
    return jsonify(
        {
            "items": items,
            "legacy_note": (
                "Seasons before 2026-05 ran on the legacy toy-coin arena mechanic and "
                "are not comparable to real paper-trading seasons. See "
                "docs/legacy-arena-history.json."
            ),
        }
    )
