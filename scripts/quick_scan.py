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
import os
import sys
from datetime import datetime

import requests

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance is required. Install with: pip install yfinance", file=sys.stderr)
    sys.exit(2)

from portfolio_config import (
    HELD_TICKERS,
    MARKET_TICKERS,
    POSITIONS,
    ALL_POSITIONS,
    ALL_TICKERS,
    TRANCHE_2_TRADES,
    TRANCHE_3_TRADES,
    Colors,
    check_tranche_2_triggers,
    check_tranche_3_triggers,
    check_price_drop_trigger,
    check_time_elapsed_trigger,
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
# Telegram Alert
# ──────────────────────────────────────────────────────────────


def _send_telegram_msg(text: str) -> bool:
    """Send a plain text message to Telegram. Returns True on success."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        return resp.status_code == 200
    except requests.RequestException:
        return False


def format_telegram_alert(
    t2_result,
    t3_result,
    pltr_fired: bool,
    pltr_drop,
    pltr_time,
    all_prices: dict[str, float],
    pnl_list: list[dict],
    now: datetime,
) -> str:
    """Format a Telegram alert message for triggered tranches."""
    lines = []
    lines.append("🚨 <b>분할매수 트리거 충족!</b>")
    lines.append(f"<i>{now.strftime('%Y-%m-%d %H:%M')} KST</i>")
    lines.append("")

    # Bigtech tranche 2
    if t2_result.any_fired:
        fired_names = [t.name for t in t2_result.triggers if t.fired is True]
        lines.append("📌 <b>빅테크 2차 매수 실행</b>")
        lines.append(f"트리거: {', '.join(fired_names)}")
        lines.append("")
        lines.append("📋 <b>매수 주문 (빅테크 2차)</b>")
        total_cost = 0.0
        for ticker, shares in TRANCHE_2_TRADES.items():
            price = all_prices.get(ticker)
            if price:
                cost = shares * price
                total_cost += cost
                lines.append(f"  {ticker:<6} {shares}주  @ ${price:,.2f}  ≈ ${cost:,.0f}")
            else:
                lines.append(f"  {ticker:<6} {shares}주  (가격 없음)")
        lines.append(f"  <b>합계: ≈ ${total_cost:,.0f}</b>")
        lines.append("")

    # Bigtech tranche 3
    if t3_result.any_fired:
        fired_names = [t.name for t in t3_result.triggers if t.fired is True]
        lines.append("📌 <b>빅테크 3차 매수 실행</b>")
        lines.append(f"트리거: {', '.join(fired_names)}")
        lines.append("")
        lines.append("📋 <b>매수 주문 (빅테크 3차)</b>")
        total_cost = 0.0
        for ticker, shares in TRANCHE_3_TRADES.items():
            price = all_prices.get(ticker)
            if price:
                cost = shares * price
                total_cost += cost
                lines.append(f"  {ticker:<6} {shares}주  @ ${price:,.2f}  ≈ ${cost:,.0f}")
            else:
                lines.append(f"  {ticker:<6} {shares}주  (가격 없음)")
        lines.append(f"  <b>합계: ≈ ${total_cost:,.0f}</b>")
        lines.append("")

    # PLTR tranche 2
    if pltr_fired:
        fired_reasons = []
        if pltr_drop.fired:
            fired_reasons.append(pltr_drop.name)
        if pltr_time.fired:
            fired_reasons.append(pltr_time.name)
        lines.append("📌 <b>PLTR 2차 매수 실행</b>")
        lines.append(f"트리거: {', '.join(fired_reasons)}")
        lines.append("")
        lines.append("📋 <b>매수 주문 (PLTR 2차)</b>")
        pltr_price = all_prices.get("PLTR")
        if pltr_price:
            cost = 6 * pltr_price
            lines.append(f"  PLTR   6주  @ ${pltr_price:,.2f}  ≈ ${cost:,.0f}")
            lines.append(f"  <b>합계: ≈ ${cost:,.0f}</b>")
        lines.append("")

    # Current P&L snapshot
    pnl_rows = [p for p in pnl_list if p["ticker"] != "TOTAL"]
    total_row = next((p for p in pnl_list if p["ticker"] == "TOTAL"), None)
    if pnl_rows:
        lines.append("💰 <b>현재 P&amp;L</b>")
        for p in pnl_rows:
            sign = "+" if p["pnl"] >= 0 else ""
            lines.append(f"  {p['ticker']:<6} ${p['current_price']:,.2f}  {sign}{p['pnl_pct']:.1f}%")
        if total_row:
            sign = "+" if total_row["pnl"] >= 0 else ""
            lines.append(f"  <b>합계  ${total_row['market_value']:,.0f}  {sign}{total_row['pnl']:,.0f} ({sign}{total_row['pnl_pct']:.1f}%)</b>")

    return "\n".join(lines)


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

    # USD 종목만 스캔 (KRW 자산 제외)
    USD_POSITIONS = {t: v for t, v in ALL_POSITIONS.items() if v.get("currency", "USD") == "USD"}
    USD_TICKERS = list(USD_POSITIONS.keys())

    # Fetch prices for all USD held tickers + market tickers
    fetch_tickers = list(set(USD_TICKERS + MARKET_TICKERS))
    price_data = fetch_prices(fetch_tickers)

    if not price_data:
        if args.json:
            print(json.dumps({"error": "Failed to fetch price data", "timestamp": now.isoformat()}))
        else:
            print("ERROR: Failed to fetch any price data. Check network connection.", file=sys.stderr)
        sys.exit(2)

    all_prices = {t: price_data[t]["price"] for t in USD_TICKERS if t in price_data}
    missing = [t for t in USD_TICKERS if t not in price_data]
    if missing:
        print(f"WARNING: Missing price data for: {', '.join(missing)}", file=sys.stderr)

    if not all_prices:
        if args.json:
            print(json.dumps({"error": "No held stock prices available", "timestamp": now.isoformat()}))
        else:
            print("ERROR: No held stock prices available.", file=sys.stderr)
        sys.exit(2)

    # Compute P&L for USD positions only
    pnl_list = compute_pnl(USD_POSITIONS, all_prices)

    # GOOGL/AMZN/MSFT triggers (price + time only)
    held_prices = {t: all_prices[t] for t in HELD_TICKERS if t in all_prices}
    t2_result = check_tranche_2_triggers(held_prices, rsi_values=None)
    t3_result = check_tranche_3_triggers()

    # Output
    if args.json:
        output = build_json_output(price_data, pnl_list, t2_result, t3_result, now)
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        C = Colors
        lines = [format_terminal_output(price_data, pnl_list, t2_result, t3_result, now)]
        lines.append(f"{C.BOLD}{'═' * 58}{C.RESET}")
        print("\n".join(lines))

    # Telegram alert — auto-send when trigger fires and env vars are set
    any_triggered = t2_result.any_fired or t3_result.any_fired or pltr_fired
    if any_triggered:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if token and chat_id:
            msg = format_telegram_alert(
                t2_result, t3_result, pltr_fired, pltr_drop, pltr_time,
                all_prices, pnl_list, now,
            )
            ok = _send_telegram_msg(msg)
            if not args.json:
                status = "✓ Telegram 알림 발송 완료" if ok else "✗ Telegram 발송 실패"
                print(status, file=sys.stderr)
        elif not args.json:
            print("(Telegram 미설정 — TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID 없음)", file=sys.stderr)

    # Exit code
    if t2_result.any_fired or t3_result.any_fired:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
