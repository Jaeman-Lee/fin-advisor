#!/usr/bin/env python3
"""CLI script to collect FRED macro economic data."""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collection.fred_data import collect_all_fred, get_macro_dashboard
from src.database.operations import DatabaseOperations
from src.database.schema import init_db
from src.utils.config import FRED_SERIES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

CATEGORIES = sorted(set(cat for _, cat, _ in FRED_SERIES.values()))


def main():
    parser = argparse.ArgumentParser(description="Collect FRED macro data")
    parser.add_argument(
        "--category",
        choices=CATEGORIES,
        help="Collect only a specific category",
    )
    parser.add_argument(
        "--series", nargs="+",
        help="Specific FRED series IDs to collect (e.g. DFF UNRATE)",
    )
    parser.add_argument(
        "--years", type=int, default=3,
        help="Lookback period in years (default: 3)",
    )
    parser.add_argument(
        "--api-key",
        help="FRED API key (or set FRED_API_KEY env var)",
    )
    parser.add_argument(
        "--list", action="store_true", dest="list_series",
        help="List available FRED series and exit",
    )
    parser.add_argument(
        "--dashboard", action="store_true",
        help="Show current macro dashboard and exit",
    )
    args = parser.parse_args()

    if args.list_series:
        print(f"\n{'Series':<18} {'Category':<16} {'Freq':<10} Name")
        print("-" * 80)
        for sid, (name, cat, freq) in sorted(FRED_SERIES.items(), key=lambda x: (x[1][1], x[0])):
            print(f"{sid:<18} {cat:<16} {freq:<10} {name}")
        print(f"\nTotal: {len(FRED_SERIES)} series")
        return

    # Ensure DB exists
    init_db()
    db = DatabaseOperations()

    if args.dashboard:
        dashboard = get_macro_dashboard(db)
        if not dashboard:
            print("No data yet. Run collection first.")
            return
        for category, items in dashboard.items():
            print(f"\n── {category.upper()} {'─' * (60 - len(category))}")
            for item in items:
                val = f"{item['value']:.2f}" if item["value"] is not None else "N/A"
                date = item["date"] or "N/A"
                print(f"  {item['series_id']:<16} {val:>12}  ({date})  {item['name']}")
        return

    # Collect
    results = collect_all_fred(
        db,
        series_ids=args.series,
        category=args.category,
        api_key=args.api_key,
        lookback_years=args.years,
    )

    # Summary
    total = sum(results.values())
    success = sum(1 for v in results.values() if v > 0)
    failed = [sid for sid, v in results.items() if v == 0]

    print(f"\n{'=' * 50}")
    print(f"FRED Collection Summary")
    print(f"  Total rows: {total}")
    print(f"  Success: {success}/{len(results)} series")
    if failed:
        print(f"  Failed: {', '.join(failed)}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
