import logging
from dataclasses import dataclass

import httpx

from polyclaw.clients.gamma import GammaClient
from polyclaw.clients.rate_limiter import clob_market_data_limiter
from polyclaw.config import settings
from polyclaw.models.market import Market

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


class DataLoader:
    """Fetches and caches historical price data for backtesting.

    Uses the CLOB API /prices-history endpoint (not Data API, which 404s).
    """

    def __init__(self, gamma: GammaClient | None = None):
        self._gamma = gamma or GammaClient()
        self._http = httpx.Client(base_url=settings.clob_base_url, timeout=30.0)
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
            clob_market_data_limiter.acquire()
            resp = self._http.get(
                "/prices-history",
                params={"market": token_id, "interval": "max", "fidelity": fidelity},
            )
            resp.raise_for_status()
            raw = resp.json().get("history", [])
            ticks = [(int(point["t"]), float(point["p"])) for point in raw]
            ticks.sort(key=lambda x: x[0])
            self._cache[cache_key] = ticks
            logger.info(
                "Loaded %d ticks for %s (%s)", len(ticks), market_question[:40] or token_id[:20], outcome
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
