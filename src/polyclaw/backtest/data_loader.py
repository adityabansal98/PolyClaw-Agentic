import logging
from dataclasses import dataclass
from typing import Protocol

import httpx
from sqlalchemy import Engine, select

from polyclaw.clients.gamma import GammaClient
from polyclaw.clients.rate_limiter import clob_market_data_limiter
from polyclaw.config import settings
from polyclaw.models.market import Market
from polyclaw.storage.schema import price_ticks

logger = logging.getLogger(__name__)


@dataclass
class MarketPriceData:
    """Historical price data for one market token."""

    token_id: str
    market_id: str
    market_question: str
    outcome: str
    ticks: list[tuple[int, float]]  # (timestamp, price) sorted chronologically
    fidelity: int


# ── Sources ────────────────────────────────────────────────────────────────


class PriceSource(Protocol):
    """Abstract price-history source. Two implementations: live CLOB HTTP, and the
    Phase 2a `price_ticks` Postgres store. The backtest engine uses whichever the
    DataLoader was constructed with; server-mode backtests always use PostgresSource
    so agents can't DDoS the CLOB."""

    def load_ticks(self, token_id: str, *, fidelity: int) -> list[tuple[int, float]]: ...


class ClobSource:
    """Legacy offline source. Hits `/prices-history` on the CLOB API directly. Used
    for local dev and one-shot backfills; NOT used by server-mode backtests (Phase 2a
    promotes PostgresSource to the prod path)."""

    def __init__(self) -> None:
        self._http = httpx.Client(base_url=settings.clob_base_url, timeout=30.0)

    def load_ticks(self, token_id: str, *, fidelity: int) -> list[tuple[int, float]]:
        clob_market_data_limiter.acquire()
        resp = self._http.get(
            "/prices-history",
            params={"market": token_id, "interval": "max", "fidelity": fidelity},
        )
        resp.raise_for_status()
        raw = resp.json().get("history", [])
        ticks = [(int(point["t"]), float(point["p"])) for point in raw]
        ticks.sort(key=lambda x: x[0])
        return ticks


class PostgresSource:
    """Phase 2a server-mode source. Reads from `price_ticks` via SQLAlchemy.

    `fidelity` is interpreted as the target sample period in seconds — ticks closer
    than `fidelity` apart are thinned (keep first). This mirrors the CLOB
    `/prices-history` fidelity parameter so the backtest engine doesn't need to know
    which source it's reading from.
    """

    def __init__(self, engine: Engine):
        self._engine = engine

    def load_ticks(self, token_id: str, *, fidelity: int) -> list[tuple[int, float]]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(price_ticks.c.ts_ms, price_ticks.c.price)
                .where(price_ticks.c.token_id == token_id)
                .order_by(price_ticks.c.ts_ms)
            ).all()
        if not rows:
            return []
        step_ms = fidelity * 1000
        out: list[tuple[int, float]] = []
        last_ts = -step_ms
        for ts_ms, price in rows:
            if ts_ms - last_ts >= step_ms:
                out.append((int(ts_ms), float(price)))
                last_ts = int(ts_ms)
        return out


# ── DataLoader ─────────────────────────────────────────────────────────────


class DataLoader:
    """Fetches and caches historical price data for backtesting.

    The source is pluggable: `ClobSource` (default, live CLOB HTTP) for local/dev,
    or `PostgresSource` (Phase 2a) for server-mode. Pass `source=PostgresSource(engine)`
    to read from `price_ticks` instead of hitting the CLOB.
    """

    def __init__(
        self,
        gamma: GammaClient | None = None,
        *,
        source: PriceSource | None = None,
    ):
        self._gamma = gamma or GammaClient()
        self._source: PriceSource = source or ClobSource()
        self._cache: dict[str, list[tuple[int, float]]] = {}

    def load_market_prices(
        self,
        token_id: str,
        market_id: str = "",
        market_question: str = "",
        outcome: str = "Yes",
        fidelity: int = 60,
    ) -> MarketPriceData:
        """Fetch price history for a single token."""
        cache_key = f"{token_id}:{fidelity}"
        if cache_key in self._cache:
            ticks = self._cache[cache_key]
        else:
            ticks = self._source.load_ticks(token_id, fidelity=fidelity)
            self._cache[cache_key] = ticks
            logger.info(
                "Loaded %d ticks for %s (%s)",
                len(ticks),
                market_question[:40] or token_id[:20],
                outcome,
            )

        return MarketPriceData(
            token_id=token_id,
            market_id=market_id,
            market_question=market_question,
            outcome=outcome,
            ticks=ticks,
            fidelity=fidelity,
        )

    def search_markets(self, query: str, limit: int = 10) -> list[Market]:
        """Search active markets by question text."""
        all_markets = []
        for offset in range(0, 500, 100):
            page = self._gamma.get_markets(limit=100, offset=offset)
            all_markets.extend(page)
            if len(page) < 100:
                break

        q_lower = query.lower()
        filtered = [m for m in all_markets if q_lower in m.question.lower()]
        filtered.sort(key=lambda m: m.volume, reverse=True)
        return filtered[:limit]

    def load_markets_by_query(
        self,
        query: str,
        fidelity: int = 60,
        limit: int = 5,
    ) -> list[MarketPriceData]:
        """Search for markets and load YES token price history for each."""
        markets = self.search_markets(query, limit=limit)
        results = []

        for m in markets:
            if not m.clob_token_ids:
                continue
            token_id = m.clob_token_ids[0]  # YES token
            outcome = m.outcomes[0] if m.outcomes else "Yes"
            try:
                data = self.load_market_prices(
                    token_id=token_id,
                    market_id=m.condition_id,
                    market_question=m.question,
                    outcome=outcome,
                    fidelity=fidelity,
                )
                if data.ticks:
                    results.append(data)
            except Exception as e:
                logger.warning("Failed to load prices for %s: %s", m.question[:40], e)

        return results
