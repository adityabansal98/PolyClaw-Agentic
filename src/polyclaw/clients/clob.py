import logging
import time

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import BookParams

from polyclaw.clients.rate_limiter import clob_batch_limiter, clob_market_data_limiter
from polyclaw.config import settings
from polyclaw.models.orderbook import OrderBook
from polyclaw.models.price import PriceSnapshot

logger = logging.getLogger(__name__)


class ClobClientWrapper:
    """Wraps py-clob-client at Level 0 (no auth, read-only)."""

    def __init__(self, base_url: str | None = None):
        self._client = ClobClient(
            host=base_url or settings.clob_base_url,
            chain_id=settings.chain_id,
        )

    def get_orderbook(self, token_id: str) -> OrderBook:
        clob_market_data_limiter.acquire()
        summary = self._client.get_order_book(token_id)
        return OrderBook.from_clob_summary(summary)

    def get_orderbooks_batch(
        self,
        token_ids: list[str],
        *,
        chunk_size: int | None = None,
    ) -> list[OrderBook]:
        chunk_size = chunk_size or settings.clob_batch_size
        results: list[OrderBook] = []

        for i in range(0, len(token_ids), chunk_size):
            chunk = token_ids[i : i + chunk_size]
            params = [BookParams(token_id=tid) for tid in chunk]

            clob_batch_limiter.acquire()
            try:
                summaries = self._client.get_order_books(params)
                for s in summaries:
                    results.append(OrderBook.from_clob_summary(s))
            except Exception:
                logger.warning(
                    "Batch orderbook fetch failed for chunk %d-%d, falling back to individual",
                    i, i + len(chunk),
                    exc_info=True,
                )
                for tid in chunk:
                    try:
                        results.append(self.get_orderbook(tid))
                    except Exception:
                        logger.warning("Failed to fetch orderbook for %s", tid[:30], exc_info=True)

            if i + chunk_size < len(token_ids):
                logger.info("Orderbook progress: %d/%d tokens", i + len(chunk), len(token_ids))

        return results

    def get_price(self, token_id: str, market_id: str = "") -> PriceSnapshot:
        clob_market_data_limiter.acquire()
        buy = self._client.get_price(token_id, side="BUY")
        sell = self._client.get_price(token_id, side="SELL")
        mid = self._client.get_midpoint(token_id)

        return PriceSnapshot(
            token_id=token_id,
            market_id=market_id,
            buy_price=float(buy.get("price", 0)),
            sell_price=float(sell.get("price", 0)),
            midpoint=float(mid.get("mid", 0)),
            timestamp=int(time.time() * 1000),
        )

    def get_prices_batch(
        self,
        token_ids: list[str],
        *,
        token_to_market: dict[str, str] | None = None,
        chunk_size: int | None = None,
    ) -> list[PriceSnapshot]:
        """Fetch prices for multiple tokens. Falls back to individual calls."""
        chunk_size = chunk_size or settings.clob_batch_size
        token_to_market = token_to_market or {}
        results: list[PriceSnapshot] = []

        for i in range(0, len(token_ids), chunk_size):
            chunk = token_ids[i : i + chunk_size]

            for tid in chunk:
                try:
                    snapshot = self.get_price(tid, market_id=token_to_market.get(tid, ""))
                    results.append(snapshot)
                except Exception:
                    logger.warning("Failed to fetch price for %s", tid[:30], exc_info=True)

            if i + chunk_size < len(token_ids):
                logger.info("Price progress: %d/%d tokens", i + len(chunk), len(token_ids))

        return results
