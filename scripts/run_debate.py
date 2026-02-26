#!/usr/bin/env python3
"""Run strategy debate for a ticker or the entire portfolio.

Usage:
    python scripts/run_debate.py                    # All held positions
    python scripts/run_debate.py --ticker GOOGL     # Single ticker
    python scripts/run_debate.py --dry-run           # No Telegram, print only
    python scripts/run_debate.py --format markdown   # Output as markdown
"""

import argparse
import json
import logging
import sys

sys.path.insert(0, ".")

from src.database.operations import DatabaseOperations
from src.debate.moderator import DebateModerator
from src.debate.router import (
    format_debate_markdown,
    format_debate_telegram,
    route_debate_results,
)


def main():
    parser = argparse.ArgumentParser(description="Run strategy debate")
    parser.add_argument("--ticker", nargs="+", help="Ticker(s) to debate")
    parser.add_argument("--dry-run", action="store_true", help="No Telegram send")
    parser.add_argument(
        "--format", choices=["text", "markdown", "json"], default="text",
        help="Output format",
    )
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    db = DatabaseOperations()
    moderator = DebateModerator(db)

    # Determine tickers
    if args.ticker:
        tickers = args.ticker
    else:
        try:
            from scripts.portfolio_config import ALL_TICKERS
            tickers = ALL_TICKERS
        except ImportError:
            print("No tickers specified and portfolio_config not found.")
            sys.exit(1)

    print(f"Running debate for {len(tickers)} ticker(s): {', '.join(tickers)}\n")

    results = []
    for ticker in tickers:
        try:
            result = moderator.run_debate(ticker, "hold_review")
            results.append(result)

            if args.format == "markdown":
                print(format_debate_markdown(result))
                print()
            elif args.format == "json":
                print(json.dumps({
                    "ticker": result.ticker,
                    "final_signal": result.final_signal.value,
                    "confidence": result.final_confidence,
                    "urgency": result.urgency.value,
                    "votes": result.vote_tally,
                    "opinions": [
                        {"agent": op.agent_name, "signal": op.signal.value,
                         "confidence": op.confidence, "rationale": op.rationale}
                        for op in result.opinions
                    ],
                }, ensure_ascii=False, indent=2))
            else:
                print(result.recommendation)
                print(f"  → Urgency: {result.urgency.value}")
                print()
        except Exception as e:
            logging.error("Debate failed for %s: %s", ticker, e)

    # Route results
    if results:
        routed = route_debate_results(results, dry_run=args.dry_run)
        print("=" * 50)
        print(f"Routed: journal={len(routed['journal'])}, "
              f"email={len(routed['email'])}, "
              f"telegram={len(routed['telegram'])}")
        if routed["telegram"]:
            if args.dry_run:
                print(f"  (dry-run) Would send Telegram for: {routed['telegram']}")
            else:
                print(f"  Sent Telegram for: {routed['telegram']}")


if __name__ == "__main__":
    main()
