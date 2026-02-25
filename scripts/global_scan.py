#!/usr/bin/env python3
"""Daytime global market scan (KST 8:00~23:00).

Monitors US futures, VIX, Asian/European markets, FX, crypto, and commodities
as leading indicators for the US portfolio (GOOGL/AMZN/MSFT).

Usage:
    python scripts/global_scan.py              # terminal output
    python scripts/global_scan.py --json       # JSON output
    python scripts/global_scan.py --no-color   # no ANSI colors

Exit codes:
    0 = normal
    1 = alert condition (VIX spike, futures sharp drop, etc.)
    2 = error
"""

import argparse
import json
import sys
from datetime import datetime

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance required. pip install yfinance", file=sys.stderr)
    sys.exit(2)

from portfolio_config import (
    POSITIONS,
    HELD_TICKERS,
    Colors,
    compute_pnl,
)

# ──────────────────────────────────────────────────────────────
# Watched Tickers
# ──────────────────────────────────────────────────────────────

GLOBAL_TICKERS = {
    # US futures — tonight's session preview
    "ES=F":     {"name": "S&P 500 선물",   "group": "us_futures"},
    "NQ=F":     {"name": "나스닥100 선물",  "group": "us_futures"},
    # Volatility
    "^VIX":     {"name": "VIX",            "group": "volatility"},
    # Asia
    "^KS11":    {"name": "KOSPI",          "group": "asia"},
    "^N225":    {"name": "닛케이225",       "group": "asia"},
    # Europe
    "^FTSE":    {"name": "FTSE 100",       "group": "europe"},
    # FX
    "USDKRW=X": {"name": "USD/KRW",       "group": "fx"},
    "DX-Y.NYB": {"name": "달러인덱스",     "group": "fx"},
    # Crypto (24/7 sentiment)
    "BTC-USD":  {"name": "Bitcoin",        "group": "crypto"},
    "ETH-USD":  {"name": "Ethereum",       "group": "crypto"},
    "SOL-USD":  {"name": "Solana",         "group": "crypto"},
    # Safe haven / commodities
    "GC=F":     {"name": "금 선물",         "group": "commodity"},
    "CL=F":     {"name": "원유 WTI",       "group": "commodity"},
}

# Alert thresholds
VIX_ELEVATED = 20
VIX_HIGH = 25
VIX_EXTREME = 30
FUTURES_DROP_ALERT_PCT = -1.0   # S&P/NQ futures drop alert
CRYPTO_DROP_ALERT_PCT = -5.0    # BTC/ETH drop alert
FX_MOVE_ALERT_PCT = 1.0        # USD/KRW sharp move


# ──────────────────────────────────────────────────────────────
# Data Fetching
# ──────────────────────────────────────────────────────────────


def fetch_global_data() -> dict[str, dict]:
    """Fetch latest data for all global tickers."""
    all_tickers = list(GLOBAL_TICKERS.keys()) + HELD_TICKERS
    results = {}

    try:
        data = yf.download(all_tickers, period="5d", interval="1d", progress=False)
    except Exception as e:
        print(f"WARNING: yfinance download failed: {e}", file=sys.stderr)
        return results

    if data.empty:
        return results

    for ticker in all_tickers:
        try:
            close_series = data["Close"][ticker].dropna()
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
# Alert Detection
# ──────────────────────────────────────────────────────────────


def detect_alerts(data: dict[str, dict]) -> list[dict]:
    """Detect alert conditions from global data."""
    alerts = []

    # VIX spike
    vix = data.get("^VIX", {})
    if vix:
        vix_price = vix["price"]
        if vix_price >= VIX_EXTREME:
            alerts.append({"level": "critical", "msg": f"VIX {vix_price:.1f} — 극단적 공포, 시장 급락 경고"})
        elif vix_price >= VIX_HIGH:
            alerts.append({"level": "warning", "msg": f"VIX {vix_price:.1f} — 높은 변동성, 방어 모드"})
        elif vix_price >= VIX_ELEVATED:
            alerts.append({"level": "info", "msg": f"VIX {vix_price:.1f} — 경계 수준"})

    # US futures sharp drop
    for ticker in ["ES=F", "NQ=F"]:
        d = data.get(ticker, {})
        if d and d["change_pct"] <= FUTURES_DROP_ALERT_PCT:
            name = GLOBAL_TICKERS[ticker]["name"]
            alerts.append({"level": "warning", "msg": f"{name} {d['change_pct']:+.1f}% — 미장 하락 개장 예상"})

    # Crypto crash (risk-off signal)
    btc = data.get("BTC-USD", {})
    if btc and btc["change_pct"] <= CRYPTO_DROP_ALERT_PCT:
        alerts.append({"level": "warning", "msg": f"BTC {btc['change_pct']:+.1f}% — 리스크오프 심리"})

    # FX sharp move (USD/KRW)
    krw = data.get("USDKRW=X", {})
    if krw and abs(krw["change_pct"]) >= FX_MOVE_ALERT_PCT:
        direction = "원화 약세(달러 강세)" if krw["change_pct"] > 0 else "원화 강세(달러 약세)"
        alerts.append({"level": "info", "msg": f"USD/KRW {krw['change_pct']:+.1f}% — {direction}"})

    return alerts


def assess_sentiment(data: dict[str, dict]) -> dict:
    """Derive overall market sentiment from global indicators."""
    signals = []

    # US futures direction
    es = data.get("ES=F", {})
    nq = data.get("NQ=F", {})
    if es:
        signals.append(es["change_pct"])
    if nq:
        signals.append(nq["change_pct"])

    # VIX inverse signal
    vix = data.get("^VIX", {})
    if vix:
        if vix["price"] < 15:
            signals.append(1.0)
        elif vix["price"] < 20:
            signals.append(0.3)
        elif vix["price"] < 25:
            signals.append(-0.5)
        else:
            signals.append(-1.5)

    # Asia as leading indicator (half weight)
    for ticker in ["^KS11", "^N225"]:
        d = data.get(ticker, {})
        if d:
            signals.append(d["change_pct"] * 0.5)

    # Crypto sentiment (quarter weight)
    btc = data.get("BTC-USD", {})
    if btc:
        signals.append(btc["change_pct"] * 0.25)

    if not signals:
        return {"score": 0, "label": "데이터 부족", "direction": "neutral"}

    avg = sum(signals) / len(signals)

    if avg > 0.5:
        label, direction = "긍정적", "bullish"
    elif avg > 0.1:
        label, direction = "약간 긍정", "slightly_bullish"
    elif avg > -0.1:
        label, direction = "중립", "neutral"
    elif avg > -0.5:
        label, direction = "약간 부정", "slightly_bearish"
    else:
        label, direction = "부정적", "bearish"

    return {"score": round(avg, 2), "label": label, "direction": direction}


# ──────────────────────────────────────────────────────────────
# Terminal Output
# ──────────────────────────────────────────────────────────────

SEP = "═" * 62
THIN = "─" * 62


def format_terminal(data: dict, pnl_list: list, alerts: list, sentiment: dict, now: datetime) -> str:
    C = Colors
    lines = []

    lines.append(f"{C.BOLD}{SEP}{C.RESET}")
    lines.append(f"{C.BOLD} GLOBAL SCAN  {now.strftime('%Y-%m-%d %H:%M')} KST{C.RESET}")
    lines.append(f"{C.BOLD}{SEP}{C.RESET}")

    # Sentiment bar
    s = sentiment
    sc = C.GREEN if s["direction"].endswith("bullish") else C.RED if s["direction"].endswith("bearish") else C.YELLOW
    lines.append(f" 센티먼트: {sc}{C.BOLD}{s['label']}{C.RESET} (score: {s['score']:+.2f})")
    lines.append(THIN)

    # Grouped display
    groups = [
        ("us_futures", "US 선물 (오늘밤 미장 방향)"),
        ("volatility", "변동성"),
        ("asia",       "아시아"),
        ("europe",     "유럽"),
        ("fx",         "환율"),
        ("crypto",     "암호화폐 (24h 심리)"),
        ("commodity",  "원자재"),
    ]

    for group_key, group_label in groups:
        group_tickers = [t for t, info in GLOBAL_TICKERS.items() if info["group"] == group_key]
        if not any(t in data for t in group_tickers):
            continue

        lines.append(f" {C.DIM}{group_label}{C.RESET}")
        for ticker in group_tickers:
            d = data.get(ticker)
            if not d:
                continue
            info = GLOBAL_TICKERS[ticker]
            chg = d["change_pct"]
            cc = C.GREEN if chg > 0 else C.RED if chg < 0 else C.DIM

            # Format price based on type
            price = d["price"]
            if ticker == "USDKRW=X":
                price_str = f"{price:,.0f}"
            elif ticker in ("BTC-USD", "ETH-USD"):
                price_str = f"${price:,.0f}"
            elif price > 10000:
                price_str = f"{price:,.0f}"
            elif price > 100:
                price_str = f"{price:,.1f}"
            else:
                price_str = f"{price:,.2f}"

            lines.append(f"   {info['name']:<14} {price_str:>10}  {cc}{chg:+.1f}%{C.RESET}")

    # Portfolio estimated impact
    held_prices = {t: data[t]["price"] for t in HELD_TICKERS if t in data}
    if held_prices:
        lines.append(THIN)
        lines.append(f" {C.DIM}보유종목 (전일 종가 기준){C.RESET}")
        for item in pnl_list:
            if item["ticker"] == "TOTAL":
                pc = C.pnl_color(item["pnl"])
                lines.append(f"   {C.BOLD}합계{C.RESET}  ${item['cost']:,.0f} → ${item['market_value']:,.0f}"
                             f"  {pc}{item['pnl']:+,.2f} ({item['pnl_pct']:+.1f}%){C.RESET}")
            else:
                pc = C.pnl_color(item["pnl"])
                lines.append(f"   {item['ticker']:<6} {item['shares']}주  "
                             f"${item['current_price']:,.2f}  {pc}{item['pnl']:+,.2f} ({item['pnl_pct']:+.1f}%){C.RESET}")

    # Alerts
    if alerts:
        lines.append(THIN)
        for a in alerts:
            if a["level"] == "critical":
                icon = f"{C.RED}{C.BOLD}⚠⚠"
            elif a["level"] == "warning":
                icon = f"{C.YELLOW}⚠ "
            else:
                icon = f"{C.CYAN}ℹ "
            lines.append(f" {icon} {a['msg']}{C.RESET}")

    # Tonight's outlook
    lines.append(THIN)
    es = data.get("ES=F", {})
    nq = data.get("NQ=F", {})
    if es and nq:
        avg_futures = (es["change_pct"] + nq["change_pct"]) / 2
        if avg_futures > 0.3:
            outlook = f"{C.GREEN}미장 상승 개장 예상 (선물 {avg_futures:+.1f}%){C.RESET}"
        elif avg_futures < -0.3:
            outlook = f"{C.RED}미장 하락 개장 예상 (선물 {avg_futures:+.1f}%){C.RESET}"
        else:
            outlook = f"{C.DIM}미장 보합 예상 (선물 {avg_futures:+.1f}%){C.RESET}"
        lines.append(f" 오늘밤: {outlook}")

    lines.append(f"{C.BOLD}{SEP}{C.RESET}")
    return "\n".join(lines)


def build_json_output(data: dict, pnl_list: list, alerts: list, sentiment: dict, now: datetime) -> dict:
    grouped = {}
    for ticker, info in GLOBAL_TICKERS.items():
        g = info["group"]
        if g not in grouped:
            grouped[g] = {}
        d = data.get(ticker)
        if d:
            grouped[g][ticker] = {"name": info["name"], **d}

    return {
        "timestamp": now.isoformat(),
        "sentiment": sentiment,
        "global_markets": grouped,
        "portfolio": [item for item in pnl_list if item["ticker"] != "TOTAL"],
        "portfolio_total": next((item for item in pnl_list if item["ticker"] == "TOTAL"), None),
        "alerts": alerts,
        "has_alert": any(a["level"] in ("critical", "warning") for a in alerts),
    }


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Daytime global market scan")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    args = parser.parse_args()

    if args.no_color or args.json:
        Colors.disable()

    now = datetime.now()

    # Fetch all global data + held stocks
    data = fetch_global_data()
    if not data:
        msg = "Failed to fetch global market data"
        if args.json:
            print(json.dumps({"error": msg, "timestamp": now.isoformat()}))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        sys.exit(2)

    # Portfolio P&L
    held_prices = {t: data[t]["price"] for t in HELD_TICKERS if t in data}
    pnl_list = compute_pnl(POSITIONS, held_prices) if held_prices else []

    # Analysis
    alerts = detect_alerts(data)
    sentiment = assess_sentiment(data)

    # Output
    if args.json:
        output = build_json_output(data, pnl_list, alerts, sentiment, now)
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(format_terminal(data, pnl_list, alerts, sentiment, now))

    # Exit code: 1 if warning/critical alerts
    has_alert = any(a["level"] in ("critical", "warning") for a in alerts)
    sys.exit(1 if has_alert else 0)


if __name__ == "__main__":
    main()
