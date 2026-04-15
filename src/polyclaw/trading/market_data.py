"""Market data provider abstraction.

The PaperTrader must NEVER call `clob.get_orderbook()` directly. It goes through
`MarketDataProvider.get_orderbook(token_id, as_of_ts)` instead. In production this is
a thin pass-through to the live CLOB. In replay mode it reads the frozen
`orderbook_snapshots` that the original trade was executed against, making byte-identical
replay possible.

This is load-bearing for Phase 1's replay invariant. Without it, the trader still
reaches live state and two replays disagree the moment the book moves.

NOTE: `as_of_ts` is required in the signature to make replay contracts explicit, even
though `LiveMarketDataProvider` ignores it (production always wants "now"). Replay
implementations use it to resolve the correct snapshot.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod

from polyclaw.clients.clob import ClobClientWrapper
from polyclaw.models.orderbook import OrderBook


class MarketDataProvider(ABC):
    """Abstract source of orderbook + price data that the trader can consult.

    Two implementations:
    - LiveMarketDataProvider: hits the CLOB (production trading)
    - ReplayMarketDataProvider: reads frozen orderbook_snapshots (tests, replay debugger)
    """

    @abstractmethod
    def get_orderbook(self, token_id: str, *, as_of_ts: int) -> OrderBook:
        """Fetch the orderbook for `token_id` at `as_of_ts` (unix ms)."""
        ...


class LiveMarketDataProvider(MarketDataProvider):
    """Production: thin pass-through to the CLOB client."""

    def __init__(self, clob: ClobClientWrapper | None = None):
        self._clob = clob or ClobClientWrapper()

    def get_orderbook(self, token_id: str, *, as_of_ts: int) -> OrderBook:
        # as_of_ts is ignored — prod always wants the current book.
        return self._clob.get_orderbook(token_id)


class ReplayMarketDataProvider(MarketDataProvider):
    """Replay: serves orderbooks from a pre-populated in-memory map.

    Used by golden-file replay tests and (eventually) the Phase 5 replay debugger UI.
    The key is `(token_id, as_of_ts)`. If an exact match isn't found, the most recent
    snapshot at or before `as_of_ts` is returned — this mirrors how replay should work
    against `orderbook_snapshots` in Postgres.
    """

    def __init__(self) -> None:
        # token_id -> sorted list of (ts_ms, OrderBook)
        self._books: dict[str, list[tuple[int, OrderBook]]] = {}

    def add(self, token_id: str, ts_ms: int, book: OrderBook) -> None:
        bucket = self._books.setdefault(token_id, [])
        bucket.append((int(ts_ms), book))
        bucket.sort(key=lambda t: t[0])

    def get_orderbook(self, token_id: str, *, as_of_ts: int) -> OrderBook:
        bucket = self._books.get(token_id)
        if not bucket:
            raise KeyError(f"no replay orderbook for token_id={token_id[:20]}")
        # Largest ts <= as_of_ts
        chosen: OrderBook | None = None
        for ts, book in bucket:
            if ts <= as_of_ts:
                chosen = book
            else:
                break
        if chosen is None:
            # Fall through: pick the earliest if nothing is at-or-before.
            chosen = bucket[0][1]
        return chosen


def orderbook_content_hash(book: OrderBook) -> str:
    """Deterministic hash of an orderbook's bids/asks for dedup in orderbook_snapshots.

    Hashes a canonical JSON form (sorted keys, no whitespace) of a minimal shape. Used
    so two identical books ingested at different timestamps can share one snapshot row.
    """
    canonical = {
        "token_id": book.token_id,
        "market_id": book.market_id,
        "bids": [[lvl.price, lvl.size] for lvl in book.bids],
        "asks": [[lvl.price, lvl.size] for lvl in book.asks],
    }
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def orderbook_to_json(book: OrderBook) -> str:
    """Serialize an OrderBook to the JSON blob stored in orderbook_snapshots.snapshot_json."""
    return json.dumps(
        {
            "token_id": book.token_id,
            "market_id": book.market_id,
            "bids": [[lvl.price, lvl.size] for lvl in book.bids],
            "asks": [[lvl.price, lvl.size] for lvl in book.asks],
            "best_bid": book.best_bid,
            "best_ask": book.best_ask,
            "midpoint": book.midpoint,
            "spread": book.spread,
            "timestamp": book.timestamp,
            "neg_risk": book.neg_risk,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def orderbook_from_json(blob: str) -> OrderBook:
    """Rehydrate an OrderBook from the JSON stored in orderbook_snapshots."""
    from polyclaw.models.orderbook import OrderLevel

    d = json.loads(blob)
    return OrderBook(
        token_id=d["token_id"],
        market_id=d["market_id"],
        bids=[OrderLevel(price=p, size=s) for p, s in d["bids"]],
        asks=[OrderLevel(price=p, size=s) for p, s in d["asks"]],
        best_bid=d.get("best_bid"),
        best_ask=d.get("best_ask"),
        midpoint=d.get("midpoint"),
        spread=d.get("spread"),
        timestamp=d.get("timestamp", 0),
        neg_risk=d.get("neg_risk", False),
    )
