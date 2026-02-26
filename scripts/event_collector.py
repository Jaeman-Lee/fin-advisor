#!/usr/bin/env python3
"""Layer 1+2: High-frequency data collector with change detection and event-driven decisions.

Collects latest market data, computes indicators, detects significant changes,
and triggers Layer 2 (debate/alerts) when events are detected.

Usage:
    python scripts/event_collector.py                    # Full cycle (L1+L2)
    python scripts/event_collector.py --dry-run          # Detect only, no alerts
    python scripts/event_collector.py --detect-only      # Layer 1 only, enqueue events
    python scripts/event_collector.py --tickers GOOGL AMZN  # Specific tickers

Exit codes:
    0 = no events detected (quiet market)
    1 = events detected and processed
    2 = error
"""

import argparse
import json
import logging
import sys

sys.path.insert(0, ".")

from src.collection.market_data import collect_market_data
from src.collection.technical_indicators import update_indicators_in_db
from src.database.operations import DatabaseOperations
from src.database.schema import init_db
from src.pipeline.change_detector import ChangeDetector
from src.pipeline.event_store import EventStore
from src.pipeline.event_triage import EventTriager, TriageDecision

logger = logging.getLogger(__name__)


def resolve_tickers(args) -> list[str]:
    """Determine which tickers to collect."""
    if args.tickers:
        return args.tickers

    tickers = set()
    try:
        from scripts.portfolio_config import ALL_TICKERS, WATCHLIST_TICKERS, MARKET_TICKERS
        tickers.update(ALL_TICKERS)
        tickers.update(WATCHLIST_TICKERS)
        tickers.update(MARKET_TICKERS)
    except ImportError:
        pass

    # Always include VIX for macro detection
    tickers.add("^VIX")
    tickers.add("^GSPC")
    return list(tickers)


def get_held_and_watchlist() -> tuple[set[str], set[str]]:
    """Get held and watchlist ticker sets from portfolio config."""
    held = set()
    watchlist = set()
    try:
        from scripts.portfolio_config import ALL_TICKERS, WATCHLIST_TICKERS
        held = set(ALL_TICKERS)
        watchlist = set(WATCHLIST_TICKERS)
    except ImportError:
        pass
    return held, watchlist


def process_decisions(db: DatabaseOperations, store: EventStore,
                      decisions: list[TriageDecision],
                      dry_run: bool = False) -> dict:
    """Execute triage decisions: run debates, send alerts."""
    from src.debate.moderator import DebateModerator
    from src.debate.router import route_debate_results

    stats = {"debate": 0, "alert": 0, "log": 0}
    debate_results = []
    moderator = None

    for decision in decisions:
        event = decision.event

        if decision.action == "debate":
            if moderator is None:
                moderator = DebateModerator(db)

            if event.event_type == "vix_spike":
                # VIX spike → debate all held positions
                held, _ = get_held_and_watchlist()
                for ticker in held:
                    try:
                        result = moderator.run_debate(ticker, decision.debate_topic)
                        debate_results.append(result)
                    except Exception as e:
                        logger.error("Debate failed for %s: %s", ticker, e)
            elif event.ticker:
                try:
                    result = moderator.run_debate(event.ticker, decision.debate_topic)
                    debate_results.append(result)
                except Exception as e:
                    logger.error("Debate failed for %s: %s", event.ticker, e)

            store.mark_processed(0, {  # event_id handled below
                "action": "debate",
                "ticker": event.ticker,
            })
            stats["debate"] += 1

        elif decision.action == "alert_only":
            logger.info("Alert: %s", event.description)
            stats["alert"] += 1

        else:
            stats["log"] += 1

    # Route debate results
    if debate_results:
        routed = route_debate_results(debate_results, dry_run=dry_run)
        logger.info(
            "Routed: journal=%d, email=%d, telegram=%d",
            len(routed["journal"]), len(routed["email"]), len(routed["telegram"]),
        )

    return stats


def main():
    parser = argparse.ArgumentParser(description="Event-driven data collector + processor")
    parser.add_argument("--tickers", nargs="+", help="Specific tickers to collect")
    parser.add_argument("--dry-run", action="store_true", help="No alerts/Telegram sent")
    parser.add_argument("--detect-only", action="store_true", help="Layer 1 only (enqueue, no L2)")
    parser.add_argument("--period-days", type=int, default=5, help="Days of data to fetch")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    # 1. Initialize
    db_path = init_db()
    db = DatabaseOperations(db_path)
    tickers = resolve_tickers(args)
    logger.info("Collecting %d tickers: %s", len(tickers), ", ".join(sorted(tickers)))

    # 2. Collect market data (lightweight: only last N days)
    try:
        results = collect_market_data(db, tickers=tickers, period_days=args.period_days)
        logger.info("Collected data for %d tickers", len(results))
    except Exception as e:
        logger.error("Data collection failed: %s", e)
        return 2

    # 3. Update technical indicators
    updated = 0
    for ticker in tickers:
        asset_id = db.get_asset_id(ticker)
        if asset_id:
            try:
                n = update_indicators_in_db(db, asset_id)
                if n:
                    updated += 1
            except Exception as e:
                logger.debug("Indicator update failed for %s: %s", ticker, e)
    logger.info("Updated indicators for %d assets", updated)

    # 4. Detect changes
    detector = ChangeDetector(db)
    events = detector.detect_all(tickers)

    if not events:
        logger.info("No significant changes detected. Quiet market.")
        return 0

    # 5. Enqueue events (with dedup)
    store = EventStore(db)
    new_events = []
    for event in events:
        dedup_hours = 24 if event.event_type == "split_buy_trigger" else 6
        if not store.is_recent_duplicate(event.event_type, event.ticker, dedup_hours):
            event_id = store.enqueue(event)
            new_events.append(event)
            logger.info("Event: [%s] %s", event.severity, event.description)
        else:
            logger.debug("Duplicate skipped: %s", event.description)

    if not new_events:
        logger.info("All events were recent duplicates.")
        return 0

    logger.info("Detected %d new events", len(new_events))

    # 6. Layer 2: Triage + Process
    if args.detect_only:
        logger.info("Detect-only mode. %d events enqueued.", len(new_events))
        return 1

    held, watchlist = get_held_and_watchlist()
    triager = EventTriager(held_tickers=held, watchlist_tickers=watchlist)
    decisions = triager.triage(new_events)

    stats = process_decisions(db, store, decisions, dry_run=args.dry_run)
    logger.info("Done: %d debate, %d alert, %d log", stats["debate"], stats["alert"], stats["log"])

    return 1


if __name__ == "__main__":
    sys.exit(main())
