import logging
import time

from polyclaw.config import settings
from polyclaw.ingestion.market_ingester import MarketIngester
from polyclaw.ingestion.price_ingester import PriceIngester
from polyclaw.storage.database import init_db

logger = logging.getLogger(__name__)


class IngestionScheduler:
    def __init__(self, db_path: str | None = None):
        self.conn = init_db(db_path)
        self.market_ingester = MarketIngester(self.conn)
        self.price_ingester = PriceIngester(self.conn)

    def run_once(self):
        """Full ingestion cycle: markets, then prices and orderbooks."""
        logger.info("=== Starting full ingestion cycle ===")
        self.market_ingester.ingest()
        self.price_ingester.ingest_prices()
        self.price_ingester.ingest_orderbooks()
        logger.info("=== Ingestion cycle complete ===")

    def run_loop(self):
        """Continuous daemon: markets every market_refresh_interval,
        prices/orderbooks every price_refresh_interval."""
        logger.info(
            "Starting daemon (market refresh=%ds, price refresh=%ds)",
            settings.market_refresh_interval,
            settings.price_refresh_interval,
        )

        last_market_fetch = 0.0
        while True:
            try:
                now = time.monotonic()

                # Refresh markets on first run or when interval elapsed
                if now - last_market_fetch >= settings.market_refresh_interval:
                    self.market_ingester.ingest()
                    last_market_fetch = time.monotonic()

                # Always refresh prices and orderbooks
                self.price_ingester.ingest_prices()
                self.price_ingester.ingest_orderbooks()

                logger.info("Cycle complete. Sleeping %ds...", settings.price_refresh_interval)
                time.sleep(settings.price_refresh_interval)

            except KeyboardInterrupt:
                logger.info("Daemon stopped by user")
                break
            except Exception:
                logger.error("Error in ingestion loop, retrying in 30s", exc_info=True)
                time.sleep(30)

    def close(self):
        self.conn.close()
