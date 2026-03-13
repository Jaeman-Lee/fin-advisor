#!/usr/bin/env python3
"""Portfolio-wide monitor: all held positions + watchlist, 24h operation.

Checks price changes, technical levels (RSI, SMA20/50), rebalancing triggers,
and KR-specific signals (foreign buying, program trading, FX).

Usage:
    python scripts/portfolio_monitor.py                # Full check, all positions
    python scripts/portfolio_monitor.py --dry-run      # No Telegram
    python scripts/portfolio_monitor.py --us-only      # US stocks only
    python scripts/portfolio_monitor.py --kr-only      # KR stocks only

Exit codes:
    0 = no alerts (quiet)
    1 = alerts triggered
"""

import argparse
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# .env 로드
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#"):
                _line = _line.removeprefix("export ")
                key, _, val = _line.partition("=")
                if key and val:
                    os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.portfolio_config import ALL_POSITIONS, WATCHLIST, CASH_BALANCES

KST = timezone(timedelta(hours=9))
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Alert thresholds ─────────────────────────────────────
PRICE_ALERT_PCT = 2.0       # 일간 ±2% 변동 시 알림
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
VIX_WARNING = 25
VIX_DANGER = 30
OIL_ORANGE = 110            # WTI $110 → ORANGE 단계
OIL_RED = 130               # WTI $130 → RED 단계

# Rebalancing triggers from debate (2026-03-12)
REBALANCE_TRIGGERS = {
    "GREEN":  {"wti_below": 85, "vix_below": 20},
    "YELLOW": {"wti_range": (95, 110), "vix_range": (25, 35)},
    "ORANGE": {"wti_above": 110, "vix_above": 35},
    "RED":    {"wti_above": 130, "vix_above": 40},
}

# Hynix-specific thresholds
HYNIX_SMA20_ALERT = True     # SMA20 이탈 경고
HYNIX_STOP_LOSS = 800_000    # 손절선


def log(msg: str):
    ts = datetime.now(KST).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def send_telegram(msg: str, dry_run: bool = False) -> bool:
    if dry_run:
        log("DRY-RUN: Telegram skipped")
        return False
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log("WARN: Telegram credentials missing")
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as e:
        log(f"Telegram error: {e}")
        return False


# ── Data Fetchers ────────────────────────────────────────

def get_stock_data(ticker: str, period: str = "3mo") -> dict | None:
    """Get price, RSI, SMA20, SMA50 for a ticker."""
    try:
        data = yf.Ticker(ticker).history(period=period)
        if data is None or len(data) < 20:
            return None

        close = data["Close"]
        curr = float(close.iloc[-1])
        prev = float(close.iloc[-2]) if len(close) >= 2 else curr

        # RSI(14)
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi_series = 100 - (100 / (1 + rs))
        rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty else None

        # SMAs
        sma20 = float(close.rolling(20).mean().iloc[-1])
        sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None

        day_chg = (curr - prev) / prev * 100 if prev else 0

        return {
            "price": curr, "prev": prev, "day_chg": day_chg,
            "rsi": rsi, "sma20": sma20, "sma50": sma50,
            "above_sma20": curr > sma20,
            "above_sma50": curr > sma50 if sma50 else None,
            "volume": int(data["Volume"].iloc[-1]),
        }
    except Exception as e:
        log(f"Data error {ticker}: {e}")
        return None


def get_market_data() -> dict:
    """Get VIX, WTI, USD/KRW."""
    result = {}
    for ticker, key in [("^VIX", "vix"), ("CL=F", "wti"), ("BZ=F", "brent"), ("USDKRW=X", "usdkrw")]:
        try:
            data = yf.Ticker(ticker).history(period="5d")
            if data is not None and len(data) >= 2:
                curr = float(data["Close"].iloc[-1])
                prev = float(data["Close"].iloc[-2])
                result[key] = {"value": curr, "prev": prev, "chg": (curr - prev) / prev * 100}
        except Exception:
            pass
    return result


def _trading_date() -> str:
    now = datetime.now(KST)
    if now.hour < 9:
        now -= timedelta(days=1)
    while now.weekday() >= 5:
        now -= timedelta(days=1)
    return now.strftime("%Y%m%d")


def _parse_number(text: str) -> float:
    text = text.strip().replace(",", "").replace("+", "")
    if not text or text == "-":
        return 0.0
    return float(text)


def get_kr_signals() -> dict:
    """Get Korean market signals: foreign buying, program trading."""
    result = {"foreign": None, "program": None}
    trd_date = _trading_date()
    headers = {"User-Agent": "Mozilla/5.0"}

    # Foreign investors
    try:
        resp = requests.get(
            f"https://finance.naver.com/sise/investorDealTrendTime.naver?bizdate={trd_date}&sosok=01",
            headers=headers, timeout=10,
        )
        if resp.status_code == 200:
            text = resp.content.decode("euc-kr", errors="replace")
            soup = BeautifulSoup(text, "html.parser")
            table = soup.find("table", class_="type_1")
            if table:
                for row in table.find_all("tr"):
                    tds = row.find_all("td")
                    if len(tds) >= 3:
                        time_str = tds[0].get_text(strip=True)
                        if ":" in time_str:
                            val = _parse_number(tds[2].get_text(strip=True))
                            result["foreign"] = {"net_eok": val, "is_buying": val > 0, "time": time_str}
                            break
    except Exception as e:
        log(f"Foreign investor error: {e}")

    # Program trading (non-arbitrage)
    try:
        resp = requests.get(
            f"https://finance.naver.com/sise/programDealTrendTime.naver?bizdate={trd_date}&sosok=",
            headers=headers, timeout=10,
        )
        if resp.status_code == 200:
            text = resp.content.decode("euc-kr", errors="replace")
            soup = BeautifulSoup(text, "html.parser")
            table = soup.find("table", class_="type_1")
            if table:
                for row in table.find_all("tr"):
                    tds = row.find_all("td")
                    if len(tds) >= 7:
                        time_str = tds[0].get_text(strip=True)
                        if ":" in time_str:
                            net = _parse_number(tds[6].get_text(strip=True))
                            result["program"] = {"net_eok": net, "is_buying": net > 0, "time": time_str}
                            break
    except Exception as e:
        log(f"Program trading error: {e}")

    return result


# ── Alert Logic ──────────────────────────────────────────

def check_position_alerts(ticker: str, pos: dict, data: dict) -> list[str]:
    """Check alerts for a single position."""
    alerts = []
    avg = pos["avg_price"]
    curr = data["price"]
    total_chg = (curr - avg) / avg * 100

    # Large daily move
    if abs(data["day_chg"]) >= PRICE_ALERT_PCT:
        direction = "급등" if data["day_chg"] > 0 else "급락"
        alerts.append(f"{ticker} {direction} {data['day_chg']:+.2f}% (현재 {curr:,.2f})")

    # RSI extremes
    if data["rsi"] is not None:
        if data["rsi"] <= RSI_OVERSOLD:
            alerts.append(f"{ticker} RSI {data['rsi']:.1f} 과매도!")
        elif data["rsi"] >= RSI_OVERBOUGHT:
            alerts.append(f"{ticker} RSI {data['rsi']:.1f} 과매수!")

    # SMA20 breach (for held positions)
    if not data["above_sma20"]:
        alerts.append(f"{ticker} SMA20({data['sma20']:,.2f}) 하방 이탈")

    # Hynix-specific
    if ticker == "000660.KS":
        if curr <= HYNIX_STOP_LOSS:
            alerts.append(f"!! 하이닉스 손절선 {HYNIX_STOP_LOSS:,}원 도달 !!")

    return alerts


def check_rebalance_stage(market: dict) -> str:
    """Determine rebalancing stage based on market data."""
    wti = market.get("wti", {}).get("value", 0)
    vix = market.get("vix", {}).get("value", 0)

    if wti >= 130 and vix >= 40:
        return "RED"
    elif wti >= 110 and vix >= 35:
        return "ORANGE"
    elif wti < 85 and vix < 20:
        return "GREEN"
    else:
        return "YELLOW"


# ── Report Formatter ─────────────────────────────────────

def format_report(positions_data: dict, market: dict, kr_signals: dict,
                  alerts: list[str], stage: str) -> str:
    now = datetime.now(KST).strftime("%m/%d %H:%M")
    lines = [f"*Portfolio Monitor*", f"_{now} KST_", ""]

    # Market overview
    vix = market.get("vix", {})
    wti = market.get("wti", {})
    brent = market.get("brent", {})
    fx = market.get("usdkrw", {})

    lines.append("*시장*")
    if vix:
        lines.append(f"VIX: {vix['value']:.2f} ({vix['chg']:+.2f}%)")
    if wti:
        lines.append(f"WTI: ${wti['value']:.2f} ({wti['chg']:+.2f}%)")
    if fx:
        lines.append(f"USD/KRW: {fx['value']:,.1f}원 ({fx['chg']:+.2f}%)")
    lines.append(f"리밸런싱: *{stage}*")
    lines.append("")

    # Positions
    lines.append("*보유종목*")
    for ticker, data in sorted(positions_data.items()):
        if data is None:
            continue
        pos = ALL_POSITIONS.get(ticker, {})
        avg = pos.get("avg_price", 0)
        total_chg = (data["price"] - avg) / avg * 100 if avg else 0
        cur = pos.get("currency", "USD")

        if cur == "KRW":
            lines.append(
                f"`{ticker:10s}` {data['price']:>10,.0f}원"
                f" 일:{data['day_chg']:+.1f}% 총:{total_chg:+.1f}%"
                f" RSI:{data['rsi']:.0f}" if data.get("rsi") else ""
            )
        else:
            name = ticker
            lines.append(
                f"`{name:6s}` ${data['price']:>8.2f}"
                f" 일:{data['day_chg']:+.1f}% 총:{total_chg:+.1f}%"
                + (f" RSI:{data['rsi']:.0f}" if data.get("rsi") else "")
            )
    lines.append("")

    # KR signals (if available)
    if kr_signals.get("foreign") or kr_signals.get("program"):
        met = 0
        lines.append("*KR 3박자*")
        f = kr_signals.get("foreign")
        p = kr_signals.get("program")
        fx_declining = fx.get("chg", 0) < 0 if fx else False

        if f:
            mark = "O" if f["is_buying"] else "X"
            met += 1 if f["is_buying"] else 0
            lines.append(f"[{mark}] 외국인: {f['net_eok']:+,.0f}억")
        if p:
            mark = "O" if p["is_buying"] else "X"
            met += 1 if p["is_buying"] else 0
            lines.append(f"[{mark}] 비차익: {p['net_eok']:+,.0f}억")
        if fx:
            mark = "O" if fx_declining else "X"
            met += 1 if fx_declining else 0
            lines.append(f"[{mark}] 환율하락: {fx['value']:,.1f}원 ({fx['chg']:+.2f}%)")
        lines.append(f">> {met}/3 충족")
        lines.append("")

    # Alerts
    if alerts:
        lines.append("*ALERTS*")
        for a in alerts:
            lines.append(f"- {a}")

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Portfolio-wide monitor")
    parser.add_argument("--dry-run", action="store_true", help="No Telegram")
    parser.add_argument("--us-only", action="store_true", help="US stocks only")
    parser.add_argument("--kr-only", action="store_true", help="KR stocks only")
    parser.add_argument("--once", action="store_true", help="Single check")
    args = parser.parse_args()

    log("=== Portfolio Monitor Start ===")

    # 1. Determine tickers
    tickers = {}
    for ticker, pos in ALL_POSITIONS.items():
        if args.us_only and pos.get("currency") == "KRW":
            continue
        if args.kr_only and pos.get("currency") == "USD":
            continue
        tickers[ticker] = pos

    log(f"Monitoring {len(tickers)} positions: {', '.join(tickers.keys())}")

    # 2. Get market data
    market = get_market_data()
    stage = check_rebalance_stage(market)
    log(f"Market: VIX={market.get('vix', {}).get('value', '?')}, "
        f"WTI=${market.get('wti', {}).get('value', '?')}, Stage={stage}")

    # 3. Get stock data + check alerts
    positions_data = {}
    all_alerts = []

    for ticker, pos in tickers.items():
        data = get_stock_data(ticker)
        positions_data[ticker] = data
        if data:
            alerts = check_position_alerts(ticker, pos, data)
            all_alerts.extend(alerts)
            log(f"{ticker}: {data['price']:,.2f} ({data['day_chg']:+.2f}%) RSI={data.get('rsi', '?')}")

    # 4. KR signals (only if KR stocks in scope)
    kr_signals = {}
    has_kr = any(p.get("currency") == "KRW" for p in tickers.values())
    if has_kr and not args.us_only:
        kr_signals = get_kr_signals()

    # 5. Stage alerts
    if stage == "ORANGE":
        all_alerts.append("ORANGE: WTI $110+ / VIX 35+ → AMZN 9주 + META 1주 매도 준비")
    elif stage == "RED":
        all_alerts.append("RED: WTI $130+ / VIX 40+ → 빅테크 50% 청산 즉시!")
    elif stage == "GREEN":
        all_alerts.append("GREEN: 3차 분할매수 실행 조건 검토")

    # 6. Format and send
    report = format_report(positions_data, market, kr_signals, all_alerts, stage)
    log(report)

    # Send Telegram if alerts exist or stage is not YELLOW
    if all_alerts or stage in ("ORANGE", "RED", "GREEN"):
        send_telegram(report, dry_run=args.dry_run)
        log(f"Alerts: {len(all_alerts)} items, Stage: {stage}")
    else:
        log("No alerts — Telegram skipped")

    return 1 if all_alerts else 0


if __name__ == "__main__":
    sys.exit(main())
