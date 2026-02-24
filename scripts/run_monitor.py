#!/usr/bin/env python3
"""Market monitoring CLI: check alerts and send Telegram notifications.

Usage:
    python scripts/run_monitor.py                  # Full run
    python scripts/run_monitor.py --dry-run        # Check alerts, print only
    python scripts/run_monitor.py --ticker GOOGL   # Check specific ticker
    python scripts/run_monitor.py --skip-refresh   # Skip data refresh
    python scripts/run_monitor.py --force          # Ignore dedup
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collection.market_data import collect_market_data
from src.collection.technical_indicators import update_indicators_in_db
from src.database.operations import DatabaseOperations
from src.monitoring.config import ACTIVE_STRATEGY
from src.monitoring.dedup import filter_duplicate_alerts, record_sent_alerts
from src.monitoring.market_monitor import run_all_market_checks
from src.monitoring.split_buy_monitor import check_split_buy_triggers
from src.monitoring.telegram_sender import send_telegram

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("monitor")


def main():
    parser = argparse.ArgumentParser(description="Market monitoring + Telegram alerts")
    parser.add_argument("--dry-run", action="store_true",
                        help="Check alerts and print, don't send Telegram")
    parser.add_argument("--force", action="store_true",
                        help="Skip dedup (send all alerts)")
    parser.add_argument("--ticker", nargs="+",
                        help="Check specific tickers only")
    parser.add_argument("--skip-refresh", action="store_true",
                        help="Skip market data refresh")
    args = parser.parse_args()

    db = DatabaseOperations()
    tickers = args.ticker or ACTIVE_STRATEGY.tickers

    # Step 1: Refresh market data (portfolio tickers only, 5 days)
    if not args.skip_refresh:
        logger.info(f"Refreshing market data for {tickers}...")
        collect_market_data(db, tickers=tickers, period_days=5)
        for ticker in tickers:
            asset_id = db.get_asset_id(ticker)
            if asset_id:
                update_indicators_in_db(db, asset_id)
        logger.info("Data refresh complete")

    # Step 2: Run all alert checks
    logger.info("Running alert checks...")
    alerts = run_all_market_checks(db, tickers)
    alerts.extend(check_split_buy_triggers(db))

    if not alerts:
        logger.info("No alerts triggered. All quiet.")
        return

    logger.info(f"Total alerts before dedup: {len(alerts)}")

    # Step 3: Dedup
    if not args.force:
        alerts = filter_duplicate_alerts(db, alerts)

    if not alerts:
        logger.info("All alerts were duplicates. Nothing to send.")
        return

    logger.info(f"Alerts to send: {len(alerts)}")

    # Step 4: Send Telegram
    success = send_telegram(alerts, dry_run=args.dry_run)

    # Step 5: Record sent alerts (unless dry-run)
    if not args.dry_run and success:
        record_sent_alerts(db, alerts)

    # Summary
    for alert in alerts:
        logger.info(f"  [{alert.priority.value}] {alert.title}")


if __name__ == "__main__":
    main()
