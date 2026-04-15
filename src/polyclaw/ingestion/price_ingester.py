"""Price ingester — Phase 2a rewrite.

What changed from Phase 0:

- Writes go to the new multi-tenant `price_ticks` (and `market_snapshots`) tables via
  SQLAlchemy Core, not the legacy single-DB `price_snapshots` upsert path. The Phase 0
  `PriceRepository` in `storage/repositories.py` remains for the ingestion-only polyclaw.db
  pipeline and will be retired in Phase 2b along with the arena.

- **Append-on-change with dedup.** Every ingest cycle fetches the latest snapshot, but
  only inserts a new `price_ticks` row if the price differs from the last tick for that
  token. This keeps the store compact during idle markets (60s cadence × 100 tokens ×
  24 hours = 144K rows/day on upper bound; dedup typically cuts this 3-5×).

- **Retention policy.** `prune_older_than(days)` deletes ticks beyond the retention
  window. Called on a cadence by the worker loop (Phase 2c). Defaults to 30 days.

- **Source tag.** Every tick carries a `source` column so rows written by the live
  ingester ("clob_live") are distinguishable from backfilled rows ("backfill") and from
  future WebSocket sources ("clob_ws").

This class is the prod write path for `price_ticks`. For reads, the backtest engine
goes through `DataLoader.PostgresSource` (see backtest/data_loader.py).
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass

from sqlalchemy import Engine, bindparam, delete, text

from polyclaw.clients.clob import ClobClientWrapper
from polyclaw.models.price import PriceSnapshot
from polyclaw.storage.db import ensure_schema
from polyclaw.storage.repositories import (
    MarketRepository,
    OrderBookRepository,
    PriceRepository,
)
from polyclaw.storage.schema import market_snapshots, price_ticks
from polyclaw.trading.clock import Clock, SystemClock

logger = logging.getLogger(__name__)


# ── Legacy Phase 0 ingester (polyclaw.db sqlite pipeline) ─────────────────
#
# This class remains for the pre-Phase-2a scheduler + CLI paths that write to the
# legacy single-DB `price_snapshots` and `orderbook_snapshots` tables. It is scheduled
# for retirement in Phase 2b alongside the Vercel cron / arena deletion. Do NOT wire
# new code to this class; use `PriceTickIngester` below.


class PriceIngester:
    """Legacy Phase 0 ingester. Writes to `price_snapshots` + `orderbook_snapshots`
    in the single ingestion sqlite DB. Retained for scheduler.py compatibility; not
    used by Phase 2a's historical store."""

    def __init__(self, conn: sqlite3.Connection, clob: ClobClientWrapper | None = None):
        self.market_repo = MarketRepository(conn)
        self.price_repo = PriceRepository(conn)
        self.orderbook_repo = OrderBookRepository(conn)
        self.clob = clob or ClobClientWrapper()

    def _get_token_map(self) -> tuple[list[str], dict[str, str]]:
        pairs = self.market_repo.get_active_token_ids()
        token_ids = [tid for tid, _ in pairs]
        token_to_market = {tid: mid for tid, mid in pairs}
        return token_ids, token_to_market

    def ingest_prices(self) -> int:
        token_ids, token_to_market = self._get_token_map()
        logger.info("Fetching prices for %d tokens...", len(token_ids))
        snapshots = self.clob.get_prices_batch(token_ids, token_to_market=token_to_market)
        count = self.price_repo.insert_snapshots(snapshots)
        logger.info("Stored %d price snapshots (legacy)", count)
        return count

    def ingest_orderbooks(self) -> int:
        token_ids, _ = self._get_token_map()
        logger.info("Fetching orderbooks for %d tokens...", len(token_ids))
        orderbooks = self.clob.get_orderbooks_batch(token_ids)
        count = self.orderbook_repo.insert_snapshots(orderbooks)
        logger.info("Stored %d orderbook snapshots (legacy)", count)
        return count


# ── Phase 2a historical tick ingester (SQLAlchemy → price_ticks) ──────────


@dataclass
class IngestResult:
    fetched: int
    inserted: int
    deduped: int


#: Default source tag for ticks written by the live ingester loop. Must match the
#: value in backfill_price_ticks.py so operators can tell backfilled vs live rows apart.
SOURCE_LIVE = "clob_live"
SOURCE_BACKFILL = "backfill"


class PriceTickIngester:
    """Append-tick price ingester backed by `price_ticks`.

    Usage (in the Phase 2c worker loop):

        ingester = PriceTickIngester(engine, clob=clob_client, clock=SystemClock())
        while True:
            ingester.ingest_tokens(token_ids)
            time.sleep(settings.price_refresh_interval)
    """

    def __init__(
        self,
        engine: Engine,
        *,
        clob: ClobClientWrapper | None = None,
        clock: Clock | None = None,
        source: str = SOURCE_LIVE,
    ):
        self.engine = engine
        self.clob = clob or ClobClientWrapper()
        self.clock = clock or SystemClock()
        self.source = source
        ensure_schema(engine)

    # ── Ingest ──────────────────────────────────────────────────

    def ingest_tokens(
        self,
        token_ids: list[str],
        *,
        token_to_market: dict[str, str] | None = None,
    ) -> IngestResult:
        """Fetch current prices for a batch of tokens and append new ticks on change."""
        if not token_ids:
            return IngestResult(fetched=0, inserted=0, deduped=0)

        token_to_market = token_to_market or {}
        snapshots = self.clob.get_prices_batch(token_ids, token_to_market=token_to_market)
        return self._write_snapshots(snapshots)

    def _write_snapshots(self, snapshots: list[PriceSnapshot]) -> IngestResult:
        """Dedup against the latest tick per token, then batch-insert the new ones."""
        if not snapshots:
            return IngestResult(fetched=0, inserted=0, deduped=0)

        ts_ms = self.clock.now_ms()
        tokens = [s.token_id for s in snapshots]
        last_prices = self._latest_prices(tokens)

        to_insert: list[dict] = []
        deduped = 0
        for snap in snapshots:
            price = snap.midpoint if snap.midpoint is not None else snap.buy_price
            if price is None:
                continue
            last = last_prices.get(snap.token_id)
            if last is not None and _eq_price(last, price):
                deduped += 1
                continue
            to_insert.append(
                {
                    "token_id": snap.token_id,
                    "ts_ms": ts_ms,
                    "price": float(price),
                    "source": self.source,
                }
            )

        if to_insert:
            with self.engine.begin() as conn:
                conn.execute(price_ticks.insert(), to_insert)

        logger.info(
            "price_ticks ingest: fetched=%d inserted=%d deduped=%d",
            len(snapshots),
            len(to_insert),
            deduped,
        )
        return IngestResult(fetched=len(snapshots), inserted=len(to_insert), deduped=deduped)

    # ── Dedup lookup ────────────────────────────────────────────

    def _latest_prices(self, token_ids: list[str]) -> dict[str, float]:
        """Return {token_id: latest_price} for each token that has any tick stored.

        Single round-trip: a correlated subquery per-token scales poorly; we use a
        window function on Postgres and a simpler GROUP BY MAX(ts_ms) join on SQLite.
        Either way, dedup happens over a small hot set — callers pass in at most a few
        hundred token_ids per cycle.
        """
        if not token_ids:
            return {}

        with self.engine.connect() as conn:
            if conn.dialect.name == "postgresql":
                # DISTINCT ON is the fast Postgres pattern here.
                sql = text(
                    """
                    SELECT DISTINCT ON (token_id) token_id, price
                    FROM price_ticks
                    WHERE token_id = ANY(:tokens)
                    ORDER BY token_id, ts_ms DESC
                    """
                )
                rows = conn.execute(sql, {"tokens": token_ids}).all()
            else:
                # SQLite: subquery for max(ts_ms) per token, then join back.
                sql = text(
                    """
                    SELECT p.token_id, p.price
                    FROM price_ticks p
                    JOIN (
                        SELECT token_id, MAX(ts_ms) AS max_ts
                        FROM price_ticks
                        WHERE token_id IN :tokens
                        GROUP BY token_id
                    ) latest
                      ON latest.token_id = p.token_id
                     AND latest.max_ts = p.ts_ms
                    """
                ).bindparams(bindparam("tokens", expanding=True))
                rows = conn.execute(sql, {"tokens": token_ids}).all()
        return {r[0]: float(r[1]) for r in rows}

    # ── Retention ───────────────────────────────────────────────

    def prune_older_than(self, days: int) -> int:
        """Delete ticks older than `days` from now. Returns the row count deleted.

        Safe to run while the ingester is writing — uses a single DELETE with a WHERE
        on `ts_ms`, and the index on `(token_id, ts_ms)` keeps it cheap. Intended to
        run hourly from the Phase 2c worker.
        """
        cutoff = self.clock.now_ms() - days * 86_400_000
        with self.engine.begin() as conn:
            result = conn.execute(delete(price_ticks).where(price_ticks.c.ts_ms < cutoff))
            deleted = result.rowcount or 0
        if deleted:
            logger.info("price_ticks pruned %d rows older than %d days", deleted, days)
        return deleted

    # ── Market snapshots (coarser companion) ────────────────────

    def snapshot_market(
        self,
        *,
        market_id: str,
        yes_price: float | None = None,
        no_price: float | None = None,
        liquidity: float | None = None,
        volume_24h: float | None = None,
        best_bid: float | None = None,
        best_ask: float | None = None,
    ) -> None:
        """Append a market_snapshots row. Called by the market ingester cadence (~10m),
        coarser than price_ticks (~60s)."""
        with self.engine.begin() as conn:
            conn.execute(
                market_snapshots.insert().values(
                    market_id=market_id,
                    ts_ms=self.clock.now_ms(),
                    yes_price=yes_price,
                    no_price=no_price,
                    liquidity=liquidity,
                    volume_24h=volume_24h,
                    best_bid=best_bid,
                    best_ask=best_ask,
                )
            )


def _eq_price(a: float, b: float, *, tol: float = 1e-9) -> bool:
    """Two CLOB prices are the same tick if they match within a tiny tolerance.

    Polymarket's tick size is 0.01 in most cases, so 1e-9 comfortably declares
    anything-is-equal when the price string round-trips identically. The threshold
    exists to absorb float serialization noise, not to merge genuinely different
    prices.
    """
    return abs(a - b) < tol
