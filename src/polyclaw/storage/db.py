"""SQLAlchemy engine factory + idempotent Phase 1 migration runner.

One code path works against both dialects:
  - SQLite (dev + tests)         via `sqlite:///path/to/file.db`
  - Postgres (prod + CI parity)  via `postgresql+psycopg://user:pass@host/db`

The `ensure_schema()` function is idempotent: running it twice is a no-op. It handles
both fresh DBs (via `metadata.create_all`) and legacy pre-Phase-1 DBs (by detecting the
old single-tenant schema, adding `agent_id` columns, and backfilling the dashboard's
rows to `DASHBOARD_AGENT_ID`).

This is the "Phase 1 migration" that the 10 mandatory tests gate on. Phase 2a will
introduce real Alembic migrations for `price_ticks` + partitioning, but for Phase 1
the bootstrapper here is enough: it handles the one-shot pre→post schema shift.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, Engine, create_engine, inspect, text

from polyclaw.storage.schema import DASHBOARD_AGENT_ID, metadata

logger = logging.getLogger(__name__)


def make_engine(url: str) -> Engine:
    """Build a SQLAlchemy engine for either SQLite or Postgres.

    Callers pass a SQLAlchemy URL directly. The config layer is responsible for
    translating `db_backend=sqlite` + `paper_db_path` into a URL.
    """
    if url.startswith("sqlite"):
        # `check_same_thread=False` because tests + the 60s sampler share the engine
        # across threads. Concurrency safety is provided by `BEGIN IMMEDIATE` (see
        # paper_trader.py); this flag just silences the sqlite3 driver check.
        engine = create_engine(
            url,
            future=True,
            connect_args={"check_same_thread": False},
        )
        # WAL is strictly better for concurrent readers while a writer is active.
        with engine.begin() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        return engine
    return create_engine(url, future=True, pool_pre_ping=True)


def is_postgres(engine_or_conn: Engine | Connection) -> bool:
    name = engine_or_conn.dialect.name if isinstance(engine_or_conn, Engine) else engine_or_conn.dialect.name
    return name == "postgresql"


@contextmanager
def begin_exclusive(conn: Connection) -> Iterator[Connection]:
    """Begin a writer-exclusive transaction on either dialect.

    - SQLite: `BEGIN IMMEDIATE` acquires the RESERVED lock up front, so concurrent
      writers serialize instead of racing and one of them raising `database is locked`.
    - Postgres: the caller is expected to use `SELECT ... FOR UPDATE` on the hot row;
      this context manager just opens a normal transaction.

    Usage:
        with engine.connect() as conn:
            with begin_exclusive(conn):
                ... mutate rows ...
    """
    if conn.dialect.name == "sqlite":
        # SQLAlchemy's default SQLite driver runs in deferred-begin mode, so we can
        # issue our own BEGIN.
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.exec_driver_sql("COMMIT")
        except BaseException:
            conn.exec_driver_sql("ROLLBACK")
            raise
    else:
        trans = conn.begin()
        try:
            yield conn
            trans.commit()
        except BaseException:
            trans.rollback()
            raise


# ── Phase 1 migration ──────────────────────────────────────────────────────


def ensure_schema(engine: Engine) -> None:
    """Idempotent: bring any DB up to the Phase 1 schema.

    Sequence (each step is a no-op if already applied):
      1. If legacy tables exist without `agent_id`, add the column (nullable), backfill
         to DASHBOARD_AGENT_ID, then mark NOT NULL where the dialect supports it.
      2. Create any missing Phase 1 tables via `metadata.create_all` (safe no-op on
         existing tables).
      3. Rebuild legacy PKs if needed (SQLite: recreate `paper_config` and
         `paper_positions` with the new composite/surrogate PK shapes).

    Running this twice is a no-op (test #1 of the mandatory 10).
    """
    with engine.begin() as conn:
        _legacy_backfill_agent_id(conn)
        _ensure_new_pk_shapes(conn)
    # metadata.create_all runs outside `begin()` because SQLAlchemy manages its own
    # DDL transaction per-table and some Postgres DDLs auto-commit.
    metadata.create_all(engine, checkfirst=True)
    logger.info("Phase 1 schema ensured on %s", engine.url.drivername)


def _table_exists(conn: Connection, name: str) -> bool:
    return inspect(conn).has_table(name)


def _column_names(conn: Connection, table: str) -> set[str]:
    return {c["name"] for c in inspect(conn).get_columns(table)}


def _legacy_backfill_agent_id(conn: Connection) -> None:
    """Add `agent_id` to legacy `paper_trades` / `paper_open_orders` and backfill.

    These two tables only need a plain ADD COLUMN + backfill — the PK shapes are not
    changing. `paper_config` and `paper_positions` are handled separately by
    `_ensure_new_pk_shapes` because they need full table rebuilds.

    Idempotent: skips any table that already has `agent_id`.
    """
    for table_name in ("paper_trades", "paper_open_orders"):
        if not _table_exists(conn, table_name):
            continue
        cols = _column_names(conn, table_name)
        if "agent_id" in cols:
            continue
        logger.info("migrating %s: adding agent_id column", table_name)
        conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN agent_id TEXT")
        conn.execute(
            text(f"UPDATE {table_name} SET agent_id = :aid WHERE agent_id IS NULL"),
            {"aid": DASHBOARD_AGENT_ID},
        )


def _ensure_new_pk_shapes(conn: Connection) -> None:
    """Rebuild legacy `paper_config` and `paper_positions` tables with Phase 1 PK shapes.

    The old shapes were:
      - paper_config(key PRIMARY KEY, value)
      - paper_positions(token_id PRIMARY KEY, ..., realized_pnl)

    The new shapes add a composite PK on (agent_id, key) and a surrogate PK +
    UNIQUE(agent_id, token_id) respectively. Altering PKs in place is awkward on
    SQLite (no DROP CONSTRAINT), so we do a rename-copy-drop dance. Skipped entirely
    if the table already has the new shape.
    """
    dialect = conn.dialect.name

    # -- paper_config --
    if _table_exists(conn, "paper_config"):
        cols = _column_names(conn, "paper_config")
        if "agent_id" not in cols:
            logger.info("migrating paper_config: rebuilding with (agent_id, key) PK")
            if dialect == "sqlite":
                conn.exec_driver_sql("ALTER TABLE paper_config RENAME TO paper_config_legacy")
                conn.exec_driver_sql(
                    """CREATE TABLE paper_config (
                        agent_id TEXT NOT NULL,
                        key TEXT NOT NULL,
                        value TEXT NOT NULL,
                        PRIMARY KEY (agent_id, key)
                    )"""
                )
                conn.exec_driver_sql(
                    f"""INSERT INTO paper_config (agent_id, key, value)
                        SELECT '{DASHBOARD_AGENT_ID}', key, value FROM paper_config_legacy"""
                )
                conn.exec_driver_sql("DROP TABLE paper_config_legacy")
            else:
                # Postgres: drop the old PK, add agent_id NOT NULL DEFAULT, add new PK.
                conn.exec_driver_sql("ALTER TABLE paper_config DROP CONSTRAINT IF EXISTS paper_config_pkey")
                conn.exec_driver_sql(
                    f"ALTER TABLE paper_config ADD COLUMN agent_id TEXT NOT NULL DEFAULT '{DASHBOARD_AGENT_ID}'"
                )
                conn.exec_driver_sql("ALTER TABLE paper_config ALTER COLUMN agent_id DROP DEFAULT")
                conn.exec_driver_sql("ALTER TABLE paper_config ADD PRIMARY KEY (agent_id, key)")

    # -- paper_positions --
    if _table_exists(conn, "paper_positions"):
        cols = _column_names(conn, "paper_positions")
        if "agent_id" not in cols:
            logger.info("migrating paper_positions: rebuilding with surrogate PK")
            if dialect == "sqlite":
                conn.exec_driver_sql("ALTER TABLE paper_positions RENAME TO paper_positions_legacy")
                conn.exec_driver_sql(
                    """CREATE TABLE paper_positions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        agent_id TEXT NOT NULL,
                        token_id TEXT NOT NULL,
                        market_id TEXT NOT NULL,
                        market_question TEXT DEFAULT '',
                        outcome TEXT DEFAULT '',
                        shares REAL NOT NULL DEFAULT 0,
                        avg_entry_price REAL NOT NULL DEFAULT 0,
                        realized_pnl REAL NOT NULL DEFAULT 0,
                        UNIQUE (agent_id, token_id)
                    )"""
                )
                conn.exec_driver_sql(
                    f"""INSERT INTO paper_positions
                        (agent_id, token_id, market_id, market_question, outcome,
                         shares, avg_entry_price, realized_pnl)
                        SELECT '{DASHBOARD_AGENT_ID}', token_id, market_id, market_question,
                               outcome, shares, avg_entry_price, realized_pnl
                        FROM paper_positions_legacy"""
                )
                conn.exec_driver_sql("DROP TABLE paper_positions_legacy")
            else:
                conn.exec_driver_sql(
                    "ALTER TABLE paper_positions DROP CONSTRAINT IF EXISTS paper_positions_pkey"
                )
                conn.exec_driver_sql(
                    f"ALTER TABLE paper_positions ADD COLUMN agent_id TEXT NOT NULL DEFAULT '{DASHBOARD_AGENT_ID}'"
                )
                conn.exec_driver_sql("ALTER TABLE paper_positions ALTER COLUMN agent_id DROP DEFAULT")
                conn.exec_driver_sql("ALTER TABLE paper_positions ADD COLUMN id SERIAL PRIMARY KEY")
                conn.exec_driver_sql(
                    "ALTER TABLE paper_positions ADD CONSTRAINT uq_paper_positions_agent_token UNIQUE (agent_id, token_id)"
                )


class AgentNotInitialized(RuntimeError):
    """Raised when a PaperTrader is asked to read for an agent with no paper_config row.

    Eng review explicitly called out that the prior code silently returned cash=0 for
    a missing row, which hides a real config bug. Phase 1 makes this loud: the agent
    registry must create the row at agent creation time.
    """


def ensure_agent_row(engine: Engine, agent_id: str, starting_balance: float) -> None:
    """Seed a `paper_config` row for a new agent. Idempotent: no-op if already present."""
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT value FROM paper_config WHERE agent_id = :a AND key = 'cash_balance'"),
            {"a": agent_id},
        ).first()
        if existing is not None:
            return
        conn.execute(
            text("INSERT INTO paper_config (agent_id, key, value) VALUES (:a, 'cash_balance', :v)"),
            {"a": agent_id, "v": str(starting_balance)},
        )
        conn.execute(
            text("INSERT INTO paper_config (agent_id, key, value) VALUES (:a, 'starting_balance', :v)"),
            {"a": agent_id, "v": str(starting_balance)},
        )
