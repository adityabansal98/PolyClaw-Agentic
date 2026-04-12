import argparse
import logging
import sys

from polyclaw.ingestion.scheduler import IngestionScheduler
from polyclaw.storage.database import init_db


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main():
    parser = argparse.ArgumentParser(
        prog="polyclaw",
        description="PolyClaw — Polymarket data ingestion agent",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument("--db", default=None, help="SQLite database path (default: polyclaw.db)")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("fetch-markets", help="Fetch all active markets from Gamma API")
    sub.add_parser("fetch-prices", help="Fetch prices for all active market tokens")
    sub.add_parser("fetch-orderbooks", help="Fetch orderbooks for all active market tokens")
    sub.add_parser("fetch-all", help="Full ingestion: markets + prices + orderbooks")
    sub.add_parser("daemon", help="Run continuous ingestion loop")

    args = parser.parse_args()
    setup_logging(args.verbose)

    scheduler = IngestionScheduler(db_path=args.db)

    try:
        if args.command == "fetch-markets":
            scheduler.market_ingester.ingest()
        elif args.command == "fetch-prices":
            scheduler.price_ingester.ingest_prices()
        elif args.command == "fetch-orderbooks":
            scheduler.price_ingester.ingest_orderbooks()
        elif args.command == "fetch-all":
            scheduler.run_once()
        elif args.command == "daemon":
            scheduler.run_loop()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        scheduler.close()


if __name__ == "__main__":
    main()
