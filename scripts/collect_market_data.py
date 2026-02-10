#!/usr/bin/env python3
"""CLI script to collect market data from yfinance and compute indicators."""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collection.market_data import collect_market_data
from src.collection.technical_indicators import update_indicators_in_db
from src.collection.macro_data import collect_all_macro
from src.collection.crypto_data import collect_crypto_data
from src.database.operations import DatabaseOperations
from src.utils.config import STOCK_TICKERS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Collect market data")
    parser.add_argument("--asset-type", choices=["stock", "bond", "commodity", "crypto", "fx", "all"],
                        default="all", help="Asset type to collect")
    parser.add_argument("--tickers", nargs="+", help="Specific tickers to collect")
    parser.add_argument("--days", type=int, default=365, help="Lookback period in days")
    parser.add_argument("--indicators", action="store_true", help="Compute technical indicators")
    args = parser.parse_args()

    db = DatabaseOperations()
    results: dict[str, int] = {}

    if args.tickers:
        logger.info(f"Collecting data for specific tickers: {args.tickers}")
        results = collect_market_data(db, tickers=args.tickers, period_days=args.days)
    elif args.asset_type == "all":
        logger.info("Collecting all asset types...")
        results.update(collect_market_data(db, tickers=STOCK_TICKERS, period_days=args.days))
        results.update(collect_all_macro(db, period_days=args.days))
        results.update(collect_crypto_data(db, period_days=args.days))
    elif args.asset_type == "stock":
        results = collect_market_data(db, tickers=STOCK_TICKERS, period_days=args.days)
    elif args.asset_type in ("bond", "commodity", "fx"):
        results = collect_all_macro(db, period_days=args.days)
    elif args.asset_type == "crypto":
        results = collect_crypto_data(db, period_days=args.days)

    # Summary
    total = sum(results.values())
    successful = sum(1 for v in results.values() if v > 0)
    logger.info(f"\nCollection complete: {total} rows for {successful}/{len(results)} tickers")

    # Compute indicators if requested
    if args.indicators:
        logger.info("\nComputing technical indicators...")
        assets = db.get_all_assets()
        for asset in assets:
            count = update_indicators_in_db(db, asset["id"])
            if count > 0:
                logger.info(f"  {asset['ticker']}: {count} rows updated with indicators")
        logger.info("Indicator computation complete.")


if __name__ == "__main__":
    main()
