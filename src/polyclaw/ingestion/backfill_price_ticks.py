"""One-shot backfill for `price_ticks` from the CLOB `/prices-history` endpoint.

Used to seed the historical tick store for a list of tokens before the live ingester
starts running, or to fill a gap if ingestion was down. Not called on any hot path;
invoked manually or from a migration runbook.

Usage:
    uv run python -m polyclaw.ingestion.backfill_price_ticks \\
        --tokens token_id_1,token_id_2,token_id_3 \\
        --fidelity 60 \\
        --db-url sqlite:///paper_trading.db

The CLI takes explicit token ids rather than hardcoding a "bootstrap season universe"
— season universes arrive in Phase 4, and baking one into this script now would be
premature. Operators pass whichever tokens they want seeded.

Rows written here carry `source='backfill'` so they're distinguishable from live-
ingested rows (`source='clob_live'`). Dedup is per-run: if you backfill the same token
range twice, the second run produces duplicate ticks — intentionally, since the CLOB
history endpoint may return different data points after time passes. If you need
idempotency, prune first or accept that the live dedup path will collapse them on
next ingest.
"""

from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import Engine

from polyclaw.backtest.data_loader import ClobSource
from polyclaw.ingestion.price_ingester import SOURCE_BACKFILL
from polyclaw.storage.db import ensure_schema, make_engine
from polyclaw.storage.schema import price_ticks

logger = logging.getLogger(__name__)


def backfill_tokens(engine: Engine, token_ids: list[str], *, fidelity: int = 60) -> int:
    """Fetch historical ticks for each token and write them to `price_ticks`.

    Returns the total row count inserted.
    """
    ensure_schema(engine)
    source = ClobSource()
    total = 0
    for token_id in token_ids:
        logger.info("backfilling %s (fidelity=%ds)", token_id[:20], fidelity)
        ticks = source.load_ticks(token_id, fidelity=fidelity)
        if not ticks:
            logger.warning("no history for %s", token_id[:20])
            continue
        rows = [
            {"token_id": token_id, "ts_ms": ts_ms, "price": price, "source": SOURCE_BACKFILL}
            for ts_ms, price in ticks
        ]
        with engine.begin() as conn:
            conn.execute(price_ticks.insert(), rows)
        logger.info("backfilled %d ticks for %s", len(rows), token_id[:20])
        total += len(rows)
    return total


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Backfill price_ticks from CLOB /prices-history")
    parser.add_argument(
        "--tokens",
        required=True,
        help="Comma-separated list of CLOB token ids to backfill",
    )
    parser.add_argument(
        "--fidelity",
        type=int,
        default=60,
        help="Sample period in seconds (passed through to /prices-history). Default 60.",
    )
    parser.add_argument(
        "--db-url",
        default="sqlite:///paper_trading.db",
        help="SQLAlchemy URL for the target DB (default: local sqlite)",
    )
    args = parser.parse_args(argv)

    token_ids = [t.strip() for t in args.tokens.split(",") if t.strip()]
    if not token_ids:
        parser.error("--tokens must be a non-empty comma-separated list")

    engine = make_engine(args.db_url)
    count = backfill_tokens(engine, token_ids, fidelity=args.fidelity)
    logger.info("backfill complete: %d rows across %d tokens", count, len(token_ids))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
