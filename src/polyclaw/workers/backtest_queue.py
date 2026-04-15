"""Postgres-backed backtest queue with `SELECT ... FOR UPDATE SKIP LOCKED`.

Why not Redis / Celery / RQ: the platform already owns a Postgres cluster
(Supabase). Adding Redis doubles the ops surface. `SKIP LOCKED` gives us the
same guarantees (single-claim semantics, no thundering herd) with one fewer
service to monitor.

Design:

- Producers (`enqueue`) insert rows with `status='queued'`.
- Workers (`claim_one`) transactionally select the oldest queued row
  `FOR UPDATE SKIP LOCKED`, flip it to `status='running'`, and return the
  claim. Two workers running in parallel will claim different rows because
  each one's `SELECT FOR UPDATE` row-locks the candidate and `SKIP LOCKED`
  tells the second worker to skip past anything already locked.
- On finish, `mark_finished` / `mark_failed` flips to terminal status and
  writes the result/error blob.

On SQLite (dev only): `SELECT FOR UPDATE` doesn't exist, but SQLite's file
lock already serializes writers, so a plain `BEGIN IMMEDIATE` + update is
equivalent for our purposes (tests exercise this path). Production always
runs on Postgres.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, func, select, text, update

from polyclaw.storage.db import begin_exclusive, ensure_schema, is_postgres
from polyclaw.storage.schema import backtest_runs
from polyclaw.trading.clock import Clock, SystemClock

logger = logging.getLogger(__name__)


class QuotaExceeded(RuntimeError):
    """Raised when an agent's backtest enqueue violates its quota.

    Carries a machine-readable `code` so the Phase 3 error contract can map it
    to a 429/403 without losing the underlying reason.
    """

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


# ── Default quota ────────────────────────────────────────────────────────


#: Per-agent quota from PLAN §7.2c item 5. Values are deliberately conservative
#: for v1; Phase 4 seasons can override per-tier.
DEFAULT_MAX_CONCURRENT = 2
DEFAULT_MAX_PER_HOUR = 60
DEFAULT_MAX_MARKETS_PER_RUN = 20


@dataclass(frozen=True)
class BacktestClaim:
    """One claimed run handed from `claim_one` to the worker loop."""

    id: str
    agent_id: str
    strategy: str
    params: dict[str, Any]
    markets: list[dict[str, Any]]
    fidelity: int
    cash: float


# ── Queue ────────────────────────────────────────────────────────────────


class BacktestQueue:
    def __init__(
        self,
        engine: Engine,
        *,
        clock: Clock | None = None,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        max_per_hour: int = DEFAULT_MAX_PER_HOUR,
        max_markets_per_run: int = DEFAULT_MAX_MARKETS_PER_RUN,
    ):
        self.engine = engine
        self.clock: Clock = clock or SystemClock()
        self.max_concurrent = max_concurrent
        self.max_per_hour = max_per_hour
        self.max_markets_per_run = max_markets_per_run
        ensure_schema(engine)

    # ── Enqueue ───────────────────────────────────────────────

    def enqueue(
        self,
        *,
        agent_id: str,
        strategy: str,
        params: dict[str, Any],
        markets: list[dict[str, Any]],
        fidelity: int = 60,
        cash: float = 10_000.0,
    ) -> str:
        """Enqueue a backtest run. Returns the run id (a uuid4).

        Raises `QuotaExceeded` with a specific `code` if the agent is over:
          - `quota.backtest_markets_per_run`
          - `quota.backtest_concurrent`
          - `quota.backtest_hourly`
        """
        if len(markets) > self.max_markets_per_run:
            raise QuotaExceeded(
                "quota.backtest_markets_per_run",
                f"max {self.max_markets_per_run} markets per run (got {len(markets)})",
                {"limit": self.max_markets_per_run, "current": len(markets)},
            )

        now_ms = self.clock.now_ms()
        one_hour_ago = now_ms - 3_600_000

        with self.engine.begin() as conn:
            # Concurrent check: how many runs are currently running/queued for this agent?
            concurrent = conn.execute(
                select(func.count())
                .select_from(backtest_runs)
                .where(backtest_runs.c.agent_id == agent_id)
                .where(backtest_runs.c.status.in_(["queued", "running"]))
            ).scalar_one()
            if concurrent >= self.max_concurrent:
                raise QuotaExceeded(
                    "quota.backtest_concurrent",
                    f"agent has {concurrent} queued/running backtests (max {self.max_concurrent})",
                    {"limit": self.max_concurrent, "current": int(concurrent)},
                )

            # Hourly check: enqueued in the last hour?
            hourly = conn.execute(
                select(func.count())
                .select_from(backtest_runs)
                .where(backtest_runs.c.agent_id == agent_id)
                .where(backtest_runs.c.enqueued_at_ms >= one_hour_ago)
            ).scalar_one()
            if hourly >= self.max_per_hour:
                raise QuotaExceeded(
                    "quota.backtest_hourly",
                    f"agent has enqueued {hourly} runs in the last hour (max {self.max_per_hour})",
                    {"limit": self.max_per_hour, "current": int(hourly)},
                )

            run_id = str(uuid.uuid4())
            conn.execute(
                backtest_runs.insert().values(
                    id=run_id,
                    agent_id=agent_id,
                    strategy=strategy,
                    params_json=json.dumps(params, sort_keys=True),
                    markets_json=json.dumps(markets),
                    fidelity=fidelity,
                    cash=cash,
                    status="queued",
                    enqueued_at_ms=now_ms,
                )
            )
        logger.info("enqueued backtest %s for agent=%s strategy=%s", run_id, agent_id, strategy)
        return run_id

    # ── Claim ─────────────────────────────────────────────────

    def claim_one(self) -> BacktestClaim | None:
        """Atomically claim the oldest queued run. Returns None if the queue is empty.

        Postgres path uses `SELECT ... FOR UPDATE SKIP LOCKED` so parallel workers
        never contend on the same row. SQLite path uses `BEGIN IMMEDIATE` +
        a plain SELECT (SQLite's file lock makes this equivalent for our single-
        writer dev scenario).
        """
        if is_postgres(self.engine):
            return self._claim_postgres()
        return self._claim_sqlite()

    def _claim_postgres(self) -> BacktestClaim | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT id, agent_id, strategy, params_json, markets_json, fidelity, cash "
                    "FROM backtest_runs "
                    "WHERE status = 'queued' "
                    "ORDER BY enqueued_at_ms ASC "
                    "LIMIT 1 FOR UPDATE SKIP LOCKED"
                )
            ).first()
            if row is None:
                return None
            now_ms = self.clock.now_ms()
            conn.execute(
                update(backtest_runs)
                .where(backtest_runs.c.id == row[0])
                .values(status="running", started_at_ms=now_ms)
            )
            return BacktestClaim(
                id=row[0],
                agent_id=row[1],
                strategy=row[2],
                params=json.loads(row[3]),
                markets=json.loads(row[4]),
                fidelity=int(row[5]),
                cash=float(row[6]),
            )

    def _claim_sqlite(self) -> BacktestClaim | None:
        with self.engine.connect() as conn, begin_exclusive(conn):
            row = conn.execute(
                select(
                    backtest_runs.c.id,
                    backtest_runs.c.agent_id,
                    backtest_runs.c.strategy,
                    backtest_runs.c.params_json,
                    backtest_runs.c.markets_json,
                    backtest_runs.c.fidelity,
                    backtest_runs.c.cash,
                )
                .where(backtest_runs.c.status == "queued")
                .order_by(backtest_runs.c.enqueued_at_ms.asc())
                .limit(1)
            ).first()
            if row is None:
                return None
            now_ms = self.clock.now_ms()
            conn.execute(
                update(backtest_runs)
                .where(backtest_runs.c.id == row[0])
                .values(status="running", started_at_ms=now_ms)
            )
            return BacktestClaim(
                id=row[0],
                agent_id=row[1],
                strategy=row[2],
                params=json.loads(row[3]),
                markets=json.loads(row[4]),
                fidelity=int(row[5]),
                cash=float(row[6]),
            )

    # ── Terminal status ───────────────────────────────────────

    def mark_finished(self, run_id: str, result: dict[str, Any]) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                update(backtest_runs)
                .where(backtest_runs.c.id == run_id)
                .values(
                    status="finished",
                    finished_at_ms=self.clock.now_ms(),
                    result_json=json.dumps(result, default=str),
                )
            )

    def mark_failed(self, run_id: str, error: dict[str, Any]) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                update(backtest_runs)
                .where(backtest_runs.c.id == run_id)
                .values(
                    status="failed",
                    finished_at_ms=self.clock.now_ms(),
                    error_json=json.dumps(error, default=str),
                )
            )

    # ── Read ──────────────────────────────────────────────────

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(backtest_runs).where(backtest_runs.c.id == run_id)).mappings().first()
        if row is None:
            return None
        return {
            "id": row["id"],
            "agent_id": row["agent_id"],
            "strategy": row["strategy"],
            "status": row["status"],
            "enqueued_at_ms": int(row["enqueued_at_ms"]),
            "started_at_ms": int(row["started_at_ms"]) if row["started_at_ms"] else None,
            "finished_at_ms": int(row["finished_at_ms"]) if row["finished_at_ms"] else None,
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error": json.loads(row["error_json"]) if row["error_json"] else None,
        }
