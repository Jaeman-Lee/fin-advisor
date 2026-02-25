#!/usr/bin/env python3
"""Track A: Lightweight intraday portfolio scan.

Quick scan of held positions — current prices, P&L, and price/time triggers.
Designed to run in <10 seconds with no DB access.

Usage:
    python scripts/quick_scan.py              # terminal output
    python scripts/quick_scan.py --json       # JSON output
    python scripts/quick_scan.py --no-color   # no ANSI colors

Exit codes:
    0 = no triggers fired
    1 = trigger(s) fired (action needed)
    2 = error (network failure, etc.)
"""

import argparse
import json
import sys
from datetime import datetime

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance is required. Install with: pip install yfinance", file=sys.stderr)
    sys.exit(2)

from portfolio_config import (
    HELD_TICKERS,
    MARKET_TICKERS,
    POSITIONS,
    INVESTED,
    REMAINING,
    TRANCHE_2_TRADES,
    TRANCHE_3_TRADES,
    Colors,
    check_tranche_2_triggers,
    check_tranche_3_triggers,
    compute_pnl,
)

# ──────────────────────────────────────────────────────────────
# Data Fetching
# ──────────────────────────────────────────────────────────────


def fetch_prices(tickers: list[str]) -> dict[str, dict]:
    """Fetch latest prices via yfinance. Returns {ticker: {price, prev_close, change_pct}}."""
    results = {}
    all_tickers = tickers.copy()

    try:
        data = yf.download(all_tickers, period="5d", interval="1d", progress=False)
    except Exception as e:
        print(f"WARNING: yfinance download failed: {e}", file=sys.stderr)
        return results

    if data.empty:
        return results

    for ticker in all_tickers:
        try:
            if len(all_tickers) == 1:
                close_series = data["Close"]
            else:
                close_series = data["Close"][ticker]

            close_series = close_series.dropna()
            if len(close_series) < 1:
                continue

            current = float(close_series.iloc[-1])
            prev = float(close_series.iloc[-2]) if len(close_series) >= 2 else current
            change_pct = (current - prev) / prev * 100 if prev != 0 else 0.0

            results[ticker] = {
                "price": current,
                "prev_close": prev,
                "change_pct": change_pct,
            }
        except (KeyError, IndexError):
            continue

    return results


# ──────────────────────────────────────────────────────────────
# Terminal Output
# ──────────────────────────────────────────────────────────────

SEPARATOR = "═" * 58
THIN_SEP = "─" * 58


def format_terminal_output(
    price_data: dict[str, dict],
    pnl_list: list[dict],
    t2_result,
    t3_result,
    now: datetime,
) -> str:
    """Format scan results for terminal display."""
    C = Colors
    lines = []

    lines.append(f"{C.BOLD}{SEPARATOR}{C.RESET}")
    lines.append(f"{C.BOLD} QUICK SCAN  {now.strftime('%Y-%m-%d %H:%M')} KST{C.RESET}")
    lines.append(f"{C.BOLD}{SEPARATOR}{C.RESET}")

    # Market overview
    sp500 = price_data.get("^GSPC", {})
    vix = price_data.get("^VIX", {})
    sp_str = ""
    if sp500:
        sp_price = sp500["price"]
        sp_chg = sp500["change_pct"]
        color = C.pnl_color(-sp_chg if sp_chg < 0 else sp_chg)  # green for up
        color = C.GREEN if sp_chg >= 0 else C.RED
        sp_str = f" S&P 500: {sp_price:,.0f} ({color}{sp_chg:+.1f}%{C.RESET})"
    vix_str = ""
    if vix:
        vix_price = vix["price"]
        vix_level = "elevated" if vix_price > 20 else "normal" if vix_price > 15 else "low"
        vix_color = C.RED if vix_price > 25 else C.YELLOW if vix_price > 20 else C.GREEN
        vix_str = f"VIX: {vix_color}{vix_price:.1f}{C.RESET} ({vix_level})"

    if sp_str or vix_str:
        parts = [p for p in [sp_str, vix_str] if p]
        lines.append("  |  ".join(parts))
        lines.append(THIN_SEP)

    # P&L table
    for item in pnl_list:
        ticker = item["ticker"]
        if ticker == "TOTAL":
            lines.append(THIN_SEP)
            pnl_c = C.pnl_color(item["pnl"])
            lines.append(
                f" {C.BOLD}TOTAL{C.RESET}   {item['shares']}주"
                f"  ${item['cost']:,.2f} → ${item['market_value']:,.2f}"
                f"  {pnl_c}{item['pnl']:+,.2f}  ({item['pnl_pct']:+.1f}%){C.RESET}"
            )
        else:
            current = item["current_price"]
            pnl_c = C.pnl_color(item["pnl"])
            lines.append(
                f" {ticker:<6} {item['shares']}주"
                f"  ${item['avg_price']:,.2f} → ${current:,.2f}"
                f"   {pnl_c}{item['pnl']:+,.2f}  ({item['pnl_pct']:+.1f}%){C.RESET}"
            )

    lines.append("")

    # Trigger status
    t2_parts = []
    for t in t2_result.triggers:
        if t.fired is True:
            t2_parts.append(f"{C.GREEN}✓ {t.name}{C.RESET}")
        elif t.fired is False:
            # Extract concise info
            if t.name == "price_drop_5pct":
                max_drop = t.data.get("max_drop_pct", 0)
                t2_parts.append(f"✗ 5% 하락 (최대 {max_drop:+.1f}%)")
            elif t.name == "time_elapsed":
                days = t.data.get("days_remaining", "?")
                target = t.data.get("target_date", "")
                t2_parts.append(f"✗ {target}까지 {days}일")
            else:
                t2_parts.append(f"✗ {t.name}")

    t3_parts = []
    for t in t3_result.triggers:
        if t.fired is True:
            t3_parts.append(f"{C.GREEN}✓ {t.name}{C.RESET}")
        elif t.fired is False:
            if t.name == "time_elapsed":
                days = t.data.get("days_remaining", "?")
                target = t.data.get("target_date", "")
                t3_parts.append(f"✗ {target}까지 {days}일")
            else:
                t3_parts.append(f"✗ {t.name}")

    fired_any = t2_result.any_fired or t3_result.any_fired
    t2_label = f"{C.GREEN}{C.BOLD}2차 매수{C.RESET}" if t2_result.any_fired else " 2차 매수"
    t3_label = f"{C.GREEN}{C.BOLD}3차 매수{C.RESET}" if t3_result.any_fired else " 3차 매수"

    lines.append(f"{t2_label}: {' | '.join(t2_parts)}")
    lines.append(f"{t3_label}: {' | '.join(t3_parts)}")

    if fired_any:
        lines.append(f" → {C.GREEN}{C.BOLD}트리거 충족! 매수 검토 필요{C.RESET}")
    else:
        lines.append(f" → 대기 유지")

    lines.append(f"{C.BOLD}{SEPARATOR}{C.RESET}")
    return "\n".join(lines)


def build_json_output(
    price_data: dict[str, dict],
    pnl_list: list[dict],
    t2_result,
    t3_result,
    now: datetime,
) -> dict:
    """Build JSON-serializable output."""
    return {
        "timestamp": now.isoformat(),
        "market": {
            ticker: data for ticker, data in price_data.items()
            if ticker in MARKET_TICKERS
        },
        "positions": [item for item in pnl_list if item["ticker"] != "TOTAL"],
        "total": next((item for item in pnl_list if item["ticker"] == "TOTAL"), None),
        "tranche_2": {
            "any_fired": t2_result.any_fired,
            "triggers": [
                {"name": t.name, "fired": t.fired, "details": t.details, "data": t.data}
                for t in t2_result.triggers
            ],
            "summary": t2_result.summary,
        },
        "tranche_3": {
            "any_fired": t3_result.any_fired,
            "triggers": [
                {"name": t.name, "fired": t.fired, "details": t.details, "data": t.data}
                for t in t3_result.triggers
            ],
            "summary": t3_result.summary,
        },
        "action_needed": t2_result.any_fired or t3_result.any_fired,
    }


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Quick portfolio scan (Track A)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    args = parser.parse_args()

    if args.no_color or args.json:
        Colors.disable()

    now = datetime.now()

    # Fetch prices for held + market tickers
    all_tickers = HELD_TICKERS + MARKET_TICKERS
    price_data = fetch_prices(all_tickers)

    if not price_data:
        if args.json:
            print(json.dumps({"error": "Failed to fetch price data", "timestamp": now.isoformat()}))
        else:
            print("ERROR: Failed to fetch any price data. Check network connection.", file=sys.stderr)
        sys.exit(2)

    # Check if we got held stock prices
    held_prices = {t: price_data[t]["price"] for t in HELD_TICKERS if t in price_data}
    missing = [t for t in HELD_TICKERS if t not in price_data]
    if missing:
        print(f"WARNING: Missing price data for: {', '.join(missing)}", file=sys.stderr)

    if not held_prices:
        if args.json:
            print(json.dumps({"error": "No held stock prices available", "timestamp": now.isoformat()}))
        else:
            print("ERROR: No held stock prices available.", file=sys.stderr)
        sys.exit(2)

    # Compute P&L
    pnl_list = compute_pnl(POSITIONS, held_prices)

    # Check triggers (quick scan: price + time only, no RSI/MACD/SMA)
    t2_result = check_tranche_2_triggers(held_prices, rsi_values=None)
    t3_result = check_tranche_3_triggers()

    # Output
    if args.json:
        output = build_json_output(price_data, pnl_list, t2_result, t3_result, now)
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(format_terminal_output(price_data, pnl_list, t2_result, t3_result, now))

    # Exit code
    if t2_result.any_fired or t3_result.any_fired:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
