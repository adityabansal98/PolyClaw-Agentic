import logging
import sqlite3

from polyclaw.clients.gamma import GammaClient
from polyclaw.storage.repositories import MarketRepository

logger = logging.getLogger(__name__)


class MarketIngester:
    def __init__(self, conn: sqlite3.Connection, gamma: GammaClient | None = None):
        self.repo = MarketRepository(conn)
        self.gamma = gamma or GammaClient()

    def ingest(self, *, active: bool = True) -> int:
        logger.info("Starting market ingestion (active=%s)...", active)
        markets = self.gamma.get_all_markets(active=active)
        count = self.repo.upsert_markets(markets)
        logger.info("Ingested %d markets (total active in DB: %d)", count, self.repo.get_market_count())
        return count
