#!/usr/bin/env python3
"""SK Hynix 5분 간격 실시간 모니터링 + 텔레그램 매수 알림.

KRX 장중(09:00~15:30 KST) 5분마다 가격/지표 체크.
매수 신호 발생 시 텔레그램으로 알림 발송.
"""

import argparse
import os
import sys
import time
import json
import requests
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

# ── Config ──────────────────────────────────────────────────
TICKER = "000660.KS"
TICKER_NAME = "SK하이닉스"
INTERVAL_SEC = 300  # 5분
KST = timezone(timedelta(hours=9))

# 매수 판단 기준 (리스크 검토 합의)
BUY_TRIGGERS = {
    "sma20_support": 918_341,       # SMA20 지지선
    "strong_support": 900_000,      # 강한 지지선
    "rsi_oversold": 40,             # RSI 과매도
    "price_drop_pct": -3.0,         # 전일 대비 -3% 이상 하락
    "stop_loss": 880_000,           # 손절선
}

# 매수 권고 조건
# 1) SMA20(918K) 지지 확인 + RSI < 55 → 매수 권고
# 2) 900K 터치 → 적극 매수 권고
# 3) 880K 이탈 → 매수 보류 (추세 이탈)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
LOG_FILE = "/data/claude/fin_advisor/logs/hynix_monitor.log"

# 알림 중복 방지
_sent_alerts = set()


def log(msg: str):
    ts = datetime.now(KST).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log("WARN: Telegram credentials missing, skip send")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown",
        }, timeout=10)
        if resp.status_code == 200:
            log("Telegram sent OK")
            return True
        else:
            log(f"Telegram error: {resp.status_code} {resp.text[:100]}")
            return False
    except Exception as e:
        log(f"Telegram exception: {e}")
        return False


def send_alert_once(key: str, msg: str):
    """같은 key로 중복 전송 방지."""
    if key in _sent_alerts:
        return
    _sent_alerts.add(key)
    send_telegram(msg)


def fetch_data():
    """1개월 일봉 + 오늘 1분봉 데이터."""
    try:
        # 일봉 (RSI, SMA 계산용)
        daily = yf.download(TICKER, period="1mo", interval="1d", progress=False)
        # 장중 (최신 가격)
        intra = yf.download(TICKER, period="1d", interval="1m", progress=False)
        return daily, intra
    except Exception as e:
        log(f"Fetch error: {e}")
        return None, None


def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def analyze(daily, intra):
    """가격/지표 분석 후 매수 신호 판단."""
    result = {
        "price": None,
        "prev_close": None,
        "change_pct": None,
        "rsi": None,
        "sma20": None,
        "sma5": None,
        "intra_high": None,
        "intra_low": None,
        "signal": None,      # "BUY", "STRONG_BUY", "HOLD", "STOP"
        "reason": "",
    }

    # 최신 장중 가격
    if intra is not None and len(intra) > 0:
        close_col = intra["Close"]
        if isinstance(close_col, pd.DataFrame):
            close_col = close_col.iloc[:, 0]
        result["price"] = float(close_col.dropna().iloc[-1])
        high_col = intra["High"]
        if isinstance(high_col, pd.DataFrame):
            high_col = high_col.iloc[:, 0]
        low_col = intra["Low"]
        if isinstance(low_col, pd.DataFrame):
            low_col = low_col.iloc[:, 0]
        result["intra_high"] = float(high_col.max())
        result["intra_low"] = float(low_col.min())

    if daily is not None and len(daily) >= 2:
        close_col = daily["Close"]
        if isinstance(close_col, pd.DataFrame):
            close_col = close_col.iloc[:, 0]
        closes = close_col.dropna()
        result["prev_close"] = float(closes.iloc[-2]) if len(closes) >= 2 else None

        # SMA
        if len(closes) >= 20:
            result["sma20"] = float(closes.rolling(20).mean().iloc[-1])
        if len(closes) >= 5:
            result["sma5"] = float(closes.rolling(5).mean().iloc[-1])

        # RSI
        rsi_series = calc_rsi(closes)
        rsi_val = rsi_series.dropna()
        if len(rsi_val) > 0:
            result["rsi"] = float(rsi_val.iloc[-1])

    # 전일 대비 변동률
    if result["price"] and result["prev_close"]:
        result["change_pct"] = (result["price"] - result["prev_close"]) / result["prev_close"] * 100

    # 매수 신호 판단
    price = result["price"]
    if price is None:
        result["signal"] = "NO_DATA"
        return result

    reasons = []

    # 1) 손절선 이탈 → 매수 보류
    if price <= BUY_TRIGGERS["stop_loss"]:
        result["signal"] = "STOP"
        result["reason"] = f"손절선 {BUY_TRIGGERS['stop_loss']:,}원 이탈. 추세 붕괴 위험. 매수 보류."
        return result

    # 2) 900K 강한 지지선 터치 → 적극 매수
    if price <= BUY_TRIGGERS["strong_support"]:
        result["signal"] = "STRONG_BUY"
        reasons.append(f"강한 지지선 {BUY_TRIGGERS['strong_support']:,}원 도달")

    # 3) SMA20 지지 + RSI 양호
    sma20 = result["sma20"]
    rsi = result["rsi"]
    if sma20 and price <= sma20 * 1.01:  # SMA20 ±1% 이내
        reasons.append(f"SMA20({sma20:,.0f}) 지지 테스트")
        if rsi and rsi < 55:
            reasons.append(f"RSI {rsi:.1f} (양호)")
            if result["signal"] != "STRONG_BUY":
                result["signal"] = "BUY"

    # 4) 전일 대비 -3% 이상 하락
    if result["change_pct"] and result["change_pct"] <= BUY_TRIGGERS["price_drop_pct"]:
        reasons.append(f"전일 대비 {result['change_pct']:.1f}% 급락")
        if result["signal"] != "STRONG_BUY":
            result["signal"] = "BUY"

    # 5) RSI 과매도
    if rsi and rsi <= BUY_TRIGGERS["rsi_oversold"]:
        reasons.append(f"RSI {rsi:.1f} 과매도")
        if result["signal"] != "STRONG_BUY":
            result["signal"] = "BUY"

    if not result["signal"]:
        result["signal"] = "HOLD"
        result["reason"] = "매수 조건 미충족. 관망."
    else:
        result["reason"] = " + ".join(reasons)

    return result


def format_status(r):
    """터미널 출력용."""
    price = f"{r['price']:,.0f}" if r["price"] else "N/A"
    chg = f"{r['change_pct']:+.2f}%" if r["change_pct"] else "N/A"
    rsi = f"{r['rsi']:.1f}" if r["rsi"] else "N/A"
    sma20 = f"{r['sma20']:,.0f}" if r["sma20"] else "N/A"
    hi = f"{r['intra_high']:,.0f}" if r["intra_high"] else "-"
    lo = f"{r['intra_low']:,.0f}" if r["intra_low"] else "-"
    return (
        f"{TICKER_NAME} {price}원 ({chg}) | RSI {rsi} | SMA20 {sma20} | "
        f"고가 {hi} / 저가 {lo} | 신호: {r['signal']}"
    )


def format_telegram_msg(r):
    sig = r["signal"]
    emoji = {"STRONG_BUY": "🔴", "BUY": "🟡", "STOP": "⛔", "HOLD": "⚪"}.get(sig, "⚪")
    price = f"{r['price']:,.0f}" if r["price"] else "N/A"
    chg = f"{r['change_pct']:+.2f}%" if r["change_pct"] else "N/A"
    rsi = f"{r['rsi']:.1f}" if r["rsi"] else "N/A"
    sma20 = f"{r['sma20']:,.0f}" if r["sma20"] else "N/A"
    hi = f"{r['intra_high']:,.0f}" if r["intra_high"] else "-"
    lo = f"{r['intra_low']:,.0f}" if r["intra_low"] else "-"
    now = datetime.now(KST).strftime("%H:%M")

    return (
        f"{emoji} *{TICKER_NAME} 매수 신호: {sig}*\n\n"
        f"현재가: *{price}원* ({chg})\n"
        f"RSI: {rsi} | SMA20: {sma20}\n"
        f"장중 고가/저가: {hi} / {lo}\n\n"
        f"사유: {r['reason']}\n\n"
        f"권고: {'1주 매수 (₩939K, 분할 1차)' if sig in ('BUY', 'STRONG_BUY') else '관망'}\n"
        f"손절선: {BUY_TRIGGERS['stop_loss']:,}원\n"
        f"시각: {now} KST"
    )


def run_once():
    """1회 체크 → 신호 판단 → Telegram 발송 → 종료.

    Exit codes: 0=HOLD/NO_DATA, 1=BUY/STRONG_BUY, 2=STOP
    """
    log(f"=== {TICKER_NAME} 1회 체크 (--once) ===")

    daily, intra = fetch_data()
    if daily is None:
        log("데이터 수집 실패.")
        return 0

    r = analyze(daily, intra)
    log(format_status(r))

    # 매수/손절 신호 시 텔레그램 발송
    if r["signal"] in ("BUY", "STRONG_BUY", "STOP"):
        send_telegram(format_telegram_msg(r))

    # Exit code
    if r["signal"] in ("BUY", "STRONG_BUY"):
        return 1
    elif r["signal"] == "STOP":
        return 2
    return 0


def main_loop():
    """기존 무한 루프 모드 (로컬 실행용)."""
    log(f"=== {TICKER_NAME} 5분 모니터링 시작 ===")
    log(f"매수 기준: SMA20 {BUY_TRIGGERS['sma20_support']:,} | "
        f"강지지 {BUY_TRIGGERS['strong_support']:,} | "
        f"손절 {BUY_TRIGGERS['stop_loss']:,}")

    cycle = 0
    while True:
        now = datetime.now(KST)

        # 장 시간 체크 (09:00~15:30 KST)
        market_open = now.replace(hour=9, minute=0, second=0)
        market_close = now.replace(hour=15, minute=30, second=0)

        if now < market_open:
            wait = (market_open - now).total_seconds()
            log(f"장 시작 전. {wait/60:.0f}분 대기...")
            time.sleep(min(wait, 300))
            continue

        if now > market_close:
            log("장 마감. 모니터링 종료.")
            break

        cycle += 1
        log(f"--- Cycle {cycle} ---")

        daily, intra = fetch_data()
        if daily is None:
            log("데이터 수집 실패. 5분 후 재시도.")
            time.sleep(INTERVAL_SEC)
            continue

        r = analyze(daily, intra)
        log(format_status(r))

        # 매수/손절 신호 시 텔레그램 발송
        if r["signal"] in ("BUY", "STRONG_BUY", "STOP"):
            price_key = f"{r['signal']}_{int(r['price'] / 10000) if r['price'] else 0}"
            send_alert_once(price_key, format_telegram_msg(r))

        time.sleep(INTERVAL_SEC)

    log("=== 모니터링 종료 ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=f"{TICKER_NAME} 5분 모니터링")
    parser.add_argument("--once", action="store_true",
                        help="1회 체크 후 종료 (GitHub Actions용)")
    args = parser.parse_args()

    if args.once:
        sys.exit(run_once())
    else:
        main_loop()
