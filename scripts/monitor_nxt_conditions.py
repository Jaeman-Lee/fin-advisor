#!/usr/bin/env python3
"""NXT 확장시간 SK하이닉스 3박자 조건 모니터링 + Telegram 알림.

3박자 조건 (모두 충족 시 기술적 반등 진입):
  1. 외국인 선물 매수 전환
  2. 프로그램 비차익 매수 유입
  3. 환율(USD/KRW) 하락

NXT 거래시간(08:00~20:00 KST) 동안 30분 간격으로 체크.
GitHub Actions에서 --once로 실행.
"""

import argparse
import os
import sys
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

KST = timezone(timedelta(hours=9))
TICKER = "000660.KS"
TICKER_NAME = "SK하이닉스"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

KRX_API = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
KRX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd",
}


def log(msg: str):
    ts = datetime.now(KST).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def send_telegram(msg: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log("WARN: Telegram credentials missing")
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            timeout=10,
        )
        if resp.status_code == 200:
            log("Telegram sent OK")
            return True
        log(f"Telegram error: {resp.status_code} {resp.text[:100]}")
        return False
    except Exception as e:
        log(f"Telegram exception: {e}")
        return False


# ── Data Fetchers ────────────────────────────────────────


def get_hynix_price() -> dict | None:
    """SK하이닉스 현재가 + 등락률."""
    try:
        daily = yf.download(TICKER, period="5d", interval="1d", progress=False)
        intra = yf.download(TICKER, period="1d", interval="1m", progress=False)

        price, prev_close, change_pct = None, None, None
        high, low = None, None

        if intra is not None and len(intra) > 0:
            c = intra["Close"]
            if isinstance(c, pd.DataFrame):
                c = c.iloc[:, 0]
            price = float(c.dropna().iloc[-1])
            h = intra["High"]
            if isinstance(h, pd.DataFrame):
                h = h.iloc[:, 0]
            high = float(h.max())
            lo = intra["Low"]
            if isinstance(lo, pd.DataFrame):
                lo = lo.iloc[:, 0]
            low = float(lo.min())

        if daily is not None and len(daily) >= 2:
            c = daily["Close"]
            if isinstance(c, pd.DataFrame):
                c = c.iloc[:, 0]
            prev_close = float(c.dropna().iloc[-2])

        if price and prev_close:
            change_pct = (price - prev_close) / prev_close * 100

        return {
            "price": price, "prev_close": prev_close,
            "change_pct": change_pct, "high": high, "low": low,
        }
    except Exception as e:
        log(f"Price error: {e}")
        return None


def get_fx_rate() -> dict | None:
    """USD/KRW 환율 + 전일 대비 방향."""
    try:
        data = yf.download("KRW=X", period="5d", interval="1d", progress=False)
        if data is None or len(data) < 2:
            return None
        c = data["Close"]
        if isinstance(c, pd.DataFrame):
            c = c.iloc[:, 0]
        vals = c.dropna()
        latest = float(vals.iloc[-1])
        prev = float(vals.iloc[-2])
        change = latest - prev
        change_pct = change / prev * 100
        return {
            "rate": latest, "prev": prev,
            "change": change, "change_pct": change_pct,
            "declining": change < 0,  # True = 원화 강세 = 조건 충족
        }
    except Exception as e:
        log(f"FX error: {e}")
        return None


def _krx_post(bld: str, extra: dict) -> dict | None:
    """KRX API POST 호출 헬퍼."""
    try:
        payload = {"bld": bld, "locale": "ko_KR", **extra}
        resp = requests.post(KRX_API, data=payload, headers=KRX_HEADERS, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        log(f"KRX API error ({bld}): {e}")
    return None


def get_foreign_futures() -> dict | None:
    """외국인 KOSPI200 선물 순매수/매도 (KRX API)."""
    today = datetime.now(KST).strftime("%Y%m%d")
    result = _krx_post("dbms/MDC/STAT/standard/MDCSTAT072", {
        "trdDd": today,
        "prodId": "KRDRVFUK2I",  # KOSPI200 선물
        "trdVolVal": "2",
        "askBid": "3",
    })
    if result and "output" in result:
        for row in result["output"]:
            nm = row.get("INVESTOR_NM", "") or row.get("INVST_NM", "")
            if "외국인" in nm:
                raw = row.get("NETBID_TRDVAL", "0") or row.get("ASK_TRDVAL", "0")
                val = float(raw.replace(",", "").replace("-", "") or "0")
                if "-" in raw:
                    val = -val
                return {"net": val, "is_buying": val > 0}
    return None


def get_foreign_stock() -> dict | None:
    """외국인 코스피 현물 순매수/매도 (KRX API, 선물 대체 참고)."""
    today = datetime.now(KST).strftime("%Y%m%d")
    result = _krx_post("dbms/MDC/STAT/standard/MDCSTAT023", {
        "trdDd": today,
        "mktId": "STK",
        "trdVolVal": "2",
        "askBid": "3",
    })
    if result and "output" in result:
        for row in result["output"]:
            nm = row.get("INVESTOR_NM", "") or row.get("INVST_NM", "")
            if "외국인" in nm:
                raw = row.get("NETBID_TRDVAL", "0")
                val = float(raw.replace(",", "") or "0")
                return {"net": val, "is_buying": val > 0}
    return None


def get_program_trading() -> dict | None:
    """프로그램 매매 (차익/비차익) 데이터 (KRX API)."""
    today = datetime.now(KST).strftime("%Y%m%d")
    result = _krx_post("dbms/MDC/STAT/standard/MDCSTAT051", {
        "trdDd": today,
        "mktId": "STK",
    })
    if result and "output" in result:
        for row in result["output"]:
            nm = row.get("PROG_NM", "") or row.get("PGM_NM", "")
            if "비차익" in nm:
                buy = float((row.get("BID_TRDVAL", "0") or "0").replace(",", "") or "0")
                sell = float((row.get("ASK_TRDVAL", "0") or "0").replace(",", "") or "0")
                net = buy - sell
                return {"net": net, "buy": buy, "sell": sell, "is_buying": net > 0}
    return None


# ── Report Formatter ─────────────────────────────────────


def format_report(price, fx, futures, program, stock_investor) -> str:
    now = datetime.now(KST).strftime("%m/%d %H:%M")
    lines = [f"*{TICKER_NAME} NXT 모니터링*", f"_{now} KST_", ""]

    # Price
    if price and price["price"]:
        chg = f"{price['change_pct']:+.2f}%" if price["change_pct"] else ""
        lines.append(f"현재가: *{price['price']:,.0f}원* ({chg})")
        if price["high"] and price["low"]:
            lines.append(f"고/저: {price['high']:,.0f} / {price['low']:,.0f}")

    lines.append("")
    lines.append("*— 3박자 조건 —*")
    lines.append("")

    met = 0

    # ① 외국인 선물 매수 전환
    if futures:
        if futures["is_buying"]:
            c1, t1 = "O", f"순매수 {futures['net']/1e8:+,.0f}억"
            met += 1
        else:
            c1, t1 = "X", f"순매도 {futures['net']/1e8:,.0f}억"
    else:
        c1, t1 = "?", "데이터 미수신"
        if stock_investor:
            tag = "순매수" if stock_investor["is_buying"] else "순매도"
            t1 += f" (현물 {tag} {stock_investor['net']/1e8:,.0f}억)"
    lines.append(f"[{c1}] 외국인 선물: {t1}")

    # ② 프로그램 비차익 매수
    if program:
        if program["is_buying"]:
            c2, t2 = "O", f"순매수 {program['net']/1e8:+,.0f}억"
            met += 1
        else:
            c2, t2 = "X", f"순매도 {program['net']/1e8:,.0f}억"
    else:
        c2, t2 = "?", "데이터 미수신"
    lines.append(f"[{c2}] 비차익 매수: {t2}")

    # ③ 환율 하락
    if fx:
        if fx["declining"]:
            c3, t3 = "O", f"{fx['rate']:,.1f}원 ({fx['change_pct']:+.2f}%) 원강"
            met += 1
        else:
            c3, t3 = "X", f"{fx['rate']:,.1f}원 ({fx['change_pct']:+.2f}%) 원약"
    else:
        c3, t3 = "?", "미확인"
    lines.append(f"[{c3}] 환율 하락: {t3}")

    # Summary
    lines.append("")
    if met == 3:
        lines.append(">> *3/3 충족! 기술적 반등 진입 검토*")
    elif met == 2:
        lines.append(f">> {met}/3 충족 -- 주시")
    else:
        lines.append(f">> {met}/3 충족 -- 관망")

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────


def run_once() -> int:
    log(f"=== {TICKER_NAME} NXT 3박자 체크 ===")

    price = get_hynix_price()
    fx = get_fx_rate()
    futures = get_foreign_futures()
    program = get_program_trading()
    stock_inv = get_foreign_stock()

    msg = format_report(price, fx, futures, program, stock_inv)
    log(msg)
    send_telegram(msg)

    met = 0
    if futures and futures["is_buying"]:
        met += 1
    if program and program["is_buying"]:
        met += 1
    if fx and fx["declining"]:
        met += 1

    return 1 if met == 3 else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NXT 3박자 모니터링")
    parser.add_argument("--once", action="store_true", help="1회 체크 후 종료")
    args = parser.parse_args()

    sys.exit(run_once())
