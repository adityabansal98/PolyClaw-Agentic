import logging
import sqlite3

from polyclaw.clients.clob import ClobClientWrapper
from polyclaw.storage.repositories import (
    MarketRepository,
    OrderBookRepository,
    PriceRepository,
)

logger = logging.getLogger(__name__)


class PriceIngester:
    def __init__(self, conn: sqlite3.Connection, clob: ClobClientWrapper | None = None):
        self.market_repo = MarketRepository(conn)
        self.price_repo = PriceRepository(conn)
        self.orderbook_repo = OrderBookRepository(conn)
        self.clob = clob or ClobClientWrapper()

    def _get_token_map(self) -> tuple[list[str], dict[str, str]]:
        """Get active token IDs and token->market mapping."""
        pairs = self.market_repo.get_active_token_ids()
        token_ids = [tid for tid, _ in pairs]
        token_to_market = {tid: mid for tid, mid in pairs}
        return token_ids, token_to_market

    def ingest_prices(self) -> int:
        token_ids, token_to_market = self._get_token_map()
        logger.info("Fetching prices for %d tokens...", len(token_ids))
        snapshots = self.clob.get_prices_batch(token_ids, token_to_market=token_to_market)
        count = self.price_repo.insert_snapshots(snapshots)
        logger.info("Stored %d price snapshots", count)
        return count

    def ingest_orderbooks(self) -> int:
        token_ids, _ = self._get_token_map()
        logger.info("Fetching orderbooks for %d tokens...", len(token_ids))
        orderbooks = self.clob.get_orderbooks_batch(token_ids)
        count = self.orderbook_repo.insert_snapshots(orderbooks)
        logger.info("Stored %d orderbook snapshots", count)
        return count
