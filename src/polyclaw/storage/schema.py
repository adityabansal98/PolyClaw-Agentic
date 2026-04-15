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


#: The dashboard's real agent id post-migration — existing single-tenant rows backfill
#: to this value. Not "__legacy__" — the dashboard continues to write under this id
#: going forward; it is a real first-class tenant.
DASHBOARD_AGENT_ID = "__dashboard__"
