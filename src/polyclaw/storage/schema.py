"""SQLAlchemy Core schema definitions — the source of truth for PaperTrader tables.

One set of table definitions works against both SQLite (dev) and Postgres (prod). This
eliminates the two-code-path trap that Phase 0's PaperTrader fell into (raw SQLite +
PostgREST via SupabaseDB, which could silently drift).

Phase 1 scope:
- `paper_config`           — per-agent kv store (cash_balance, starting_balance)
- `paper_trades`           — fill log (multi-tenant)
- `paper_positions`        — open positions (multi-tenant, surrogate PK)
- `paper_open_orders`      — pending limit orders (multi-tenant)
- `audit_log`              — every order's request/response hash + snapshot pointers
- `orderbook_snapshots`    — frozen order books, dedup'd on content_hash
- `portfolio_snapshots`    — equity-curve time series
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)

metadata = MetaData()


paper_config = Table(
    "paper_config",
    metadata,
    # Composite PK: (agent_id, key). Each agent has its own cash_balance row.
    # Phase 1 migration drops the old `PRIMARY KEY (key)` and replaces it with this.
    Column("agent_id", String, primary_key=True, nullable=False),
    Column("key", String, primary_key=True, nullable=False),
    Column("value", String, nullable=False),
)


paper_trades = Table(
    "paper_trades",
    metadata,
    Column("id", String, primary_key=True),
    Column("agent_id", String, nullable=False),
    Column("token_id", String, nullable=False),
    Column("market_id", String, nullable=False),
    Column("market_question", String, server_default=""),
    Column("outcome", String, server_default=""),
    Column("side", String, nullable=False),
    Column("order_type", String, nullable=False),
    Column("requested_price", Float),
    Column("filled_price", Float),
    Column("filled_size", Float),
    Column("total_cost", Float),
    Column("fee", Float, nullable=False, server_default="0"),
    Column("status", String, nullable=False),
    Column("timestamp", BigInteger, nullable=False),
    Index("idx_paper_trades_agent_token", "agent_id", "token_id"),
    Index("idx_paper_trades_agent_ts", "agent_id", "timestamp"),
)


paper_positions = Table(
    "paper_positions",
    metadata,
    # Surrogate auto-id PK (Phase 1 migration replaces the old `PRIMARY KEY (token_id)`
    # which collided across agents).
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("agent_id", String, nullable=False),
    Column("token_id", String, nullable=False),
    Column("market_id", String, nullable=False),
    Column("market_question", String, server_default=""),
    Column("outcome", String, server_default=""),
    Column("shares", Float, nullable=False, server_default="0"),
    Column("avg_entry_price", Float, nullable=False, server_default="0"),
    Column("realized_pnl", Float, nullable=False, server_default="0"),
    UniqueConstraint("agent_id", "token_id", name="uq_paper_positions_agent_token"),
    Index("idx_paper_positions_agent_token", "agent_id", "token_id"),
)


paper_open_orders = Table(
    "paper_open_orders",
    metadata,
    Column("id", String, primary_key=True),
    Column("agent_id", String, nullable=False),
    Column("token_id", String, nullable=False),
    Column("market_id", String, nullable=False),
    Column("market_question", String, server_default=""),
    Column("outcome", String, server_default=""),
    Column("side", String, nullable=False),
    Column("price", Float, nullable=False),
    Column("size", Float, nullable=False),
    Column("filled_size", Float, nullable=False, server_default="0"),
    Column("timestamp", BigInteger, nullable=False),
    Index("idx_paper_open_orders_agent_token", "agent_id", "token_id"),
)


orderbook_snapshots = Table(
    "orderbook_snapshots",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("token_id", String, nullable=False),
    Column("ts_ms", BigInteger, nullable=False),
    Column("snapshot_json", String, nullable=False),
    Column("content_hash", String, nullable=False),
    # Dedup: two identical books ingested at different times share one row (by hash).
    UniqueConstraint("content_hash", name="uq_orderbook_snapshots_hash"),
    Index("idx_orderbook_snapshots_token_ts", "token_id", "ts_ms"),
)


audit_log = Table(
    "audit_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("agent_id", String, nullable=False),
    Column("ts_ms", BigInteger, nullable=False),
    Column("endpoint", String, nullable=False),
    Column("request_hash", String, nullable=False),
    Column("response_hash", String, nullable=False),
    # FK to orderbook_snapshots.id — the exact snapshot the order was executed against.
    # Not a DB-level FK (SQLite ALTER semantics make it annoying); enforced by code.
    Column("orderbook_snapshot_id", Integer),
    Column("price_tick_id", Integer),  # reserved for Phase 2a; nullable in Phase 1
    Column("season_id", String),
    Column("request_id", String, nullable=False),
    Index("idx_audit_log_agent_ts", "agent_id", "ts_ms"),
    Index("idx_audit_log_request_id", "request_id"),
)


portfolio_snapshots = Table(
    "portfolio_snapshots",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("agent_id", String, nullable=False),
    Column("ts_ms", BigInteger, nullable=False),
    Column("cash", Float, nullable=False),
    Column("position_value", Float, nullable=False),
    Column("total_equity", Float, nullable=False),
    Column("realized_pnl", Float, nullable=False),
    Column("unrealized_pnl", Float, nullable=False),
    Index("idx_portfolio_snapshots_agent_ts", "agent_id", "ts_ms"),
)


# ── Phase 2b: agent registry ─────────────────────────────────────────────


agents = Table(
    "agents",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("owner_contact", String, server_default=""),
    Column("created_at", BigInteger, nullable=False),
    # "active" | "revoked" | "draft"
    Column("status", String, nullable=False, server_default="active"),
    # FK to seasons.id once Phase 4 lands; nullable until then.
    Column("season_id", String),
    Column("starting_balance", Float, nullable=False, server_default="10000"),
    # "hosted_inprocess" | "external_http" | "external_mcp"
    Column("tier", String, nullable=False, server_default="hosted_inprocess"),
    UniqueConstraint("name", name="uq_agents_name"),
    Index("idx_agents_status", "status"),
)


agent_keys = Table(
    "agent_keys",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("agent_id", String, nullable=False),
    # SHA256 hex of the bearer token. The plaintext token is shown to the user
    # exactly once at creation and never persisted.
    Column("key_hash", String, nullable=False),
    Column("created_at", BigInteger, nullable=False),
    Column("last_used_at", BigInteger),
    Column("revoked_at", BigInteger),
    UniqueConstraint("key_hash", name="uq_agent_keys_hash"),
    Index("idx_agent_keys_agent", "agent_id"),
)


# ── Phase 2a: historical tick store ──────────────────────────────────────


price_ticks = Table(
    "price_ticks",
    metadata,
    # The surrogate id exists so audit_log.price_tick_id can FK here without coupling
    # to (token_id, ts_ms). On Postgres the *physical* storage is partitioned by hash
    # on token_id (see `ensure_schema` for the partition DDL); SQLAlchemy can't express
    # partition clauses directly, so the Table definition is the logical shape and the
    # partitioning is layered on during ensure_schema().
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("token_id", String, nullable=False),
    Column("ts_ms", BigInteger, nullable=False),
    Column("price", Float, nullable=False),
    # Where the tick came from: "clob_price_history", "clob_snapshot", "backfill", etc.
    # Kept explicit so backfilled + live-ingested rows are distinguishable.
    Column("source", String, nullable=False, server_default="clob"),
    Index("idx_price_ticks_token_ts", "token_id", "ts_ms"),
)


market_snapshots = Table(
    "market_snapshots",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("market_id", String, nullable=False),
    Column("ts_ms", BigInteger, nullable=False),
    Column("yes_price", Float),
    Column("no_price", Float),
    Column("liquidity", Float),
    Column("volume_24h", Float),
    Column("best_bid", Float),
    Column("best_ask", Float),
    Index("idx_market_snapshots_market_ts", "market_id", "ts_ms"),
)


# ── Phase 2c: async backtest queue ───────────────────────────────────────


backtest_runs = Table(
    "backtest_runs",
    metadata,
    Column("id", String, primary_key=True),
    Column("agent_id", String, nullable=False),
    Column("strategy", String, nullable=False),
    # JSON string — strategy-specific params dict. Stored as String (TEXT) rather
    # than JSONB so SQLite and Postgres share one column definition.
    Column("params_json", String, nullable=False, server_default="{}"),
    # JSON string — [{"token_id":..., "market_id":..., "question":..., "outcome":...}, ...]
    Column("markets_json", String, nullable=False, server_default="[]"),
    Column("fidelity", Integer, nullable=False, server_default="60"),
    Column("cash", Float, nullable=False, server_default="10000"),
    # "queued" | "running" | "finished" | "failed"
    Column("status", String, nullable=False, server_default="queued"),
    Column("enqueued_at_ms", BigInteger, nullable=False),
    Column("started_at_ms", BigInteger),
    Column("finished_at_ms", BigInteger),
    # JSON string — BacktestResult.model_dump() on success
    Column("result_json", String),
    # JSON string — {"type":..., "message":...} on failure
    Column("error_json", String),
    Index("idx_backtest_runs_status_enqueued", "status", "enqueued_at_ms"),
    Index("idx_backtest_runs_agent_enqueued", "agent_id", "enqueued_at_ms"),
)


#: The dashboard's real agent id post-migration — existing single-tenant rows backfill
#: to this value. Not "__legacy__" — the dashboard continues to write under this id
#: going forward; it is a real first-class tenant.
DASHBOARD_AGENT_ID = "__dashboard__"

#: Number of hash partitions used for `price_ticks` on Postgres. Chosen for v1 —
#: with 16 partitions and ~100 active tokens per season, each partition holds ~6-7
#: tokens' worth of ticks. Large enough to spread write load; small enough that
#: per-partition index maintenance is cheap.
PRICE_TICKS_PARTITION_COUNT = 16
