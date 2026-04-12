import logging

import httpx

from polyclaw.clients.rate_limiter import data_api_limiter
from polyclaw.config import settings

logger = logging.getLogger(__name__)


class DataApiClient:
    """Client for the Polymarket Data API (historical data, positions, trades)."""

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or settings.data_base_url
        self._client = httpx.Client(base_url=self.base_url, timeout=30.0)

    def get_price_history(
        self,
        token_id: str,
        *,
        fidelity: int = 60,  # minutes
    ) -> list[dict]:
        """Fetch historical price data for a token.

        Args:
            token_id: The CLOB token ID.
            fidelity: Time granularity in minutes (1, 5, 15, 60, 1440).
        """
        data_api_limiter.acquire()
        resp = self._client.get(
            "/prices-history",
            params={"market": token_id, "interval": "all", "fidelity": fidelity},
        )
        resp.raise_for_status()
        return resp.json().get("history", [])

    def get_trades(
        self,
        market_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        data_api_limiter.acquire()
        resp = self._client.get(
            "/trades",
            params={"market": market_id, "limit": limit, "offset": offset},
        )
        resp.raise_for_status()
        return resp.json()

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
