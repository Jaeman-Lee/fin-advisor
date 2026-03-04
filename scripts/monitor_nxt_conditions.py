#!/usr/bin/env python3
"""NXT 확장시간 SK하이닉스 3박자 조건 모니터링 + Telegram 알림.

3박자 조건 (모두 충족 시 기술적 반등 진입):
  1. 외국인 순매수 전환 (코스피 현물 기준)
  2. 프로그램 비차익 매수 유입
  3. 환율(USD/KRW) 하락

데이터 소스:
  - 외국인/프로그램 매매: NAVER Finance (HTML 파싱)
  - 환율/가격: yfinance
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
from bs4 import BeautifulSoup

KST = timezone(timedelta(hours=9))
TICKER = "000660.KS"
TICKER_NAME = "SK하이닉스"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

NAVER_HEADERS = {"User-Agent": "Mozilla/5.0"}


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


def _trading_date() -> str:
    """오늘 or 최근 거래일 (장전이면 전일, 주말 건너뜀)."""
    now = datetime.now(KST)
    if now.hour < 9:
        now -= timedelta(days=1)
    while now.weekday() >= 5:
        now -= timedelta(days=1)
    return now.strftime("%Y%m%d")


def _parse_number(text: str) -> float:
    """숫자 문자열 파싱 (쉼표, +/- 처리)."""
    text = text.strip().replace(",", "").replace("+", "")
    if not text or text == "-":
        return 0.0
    return float(text)


# ── Data Fetchers ────────────────────────────────────────


def get_hynix_price() -> dict | None:
    """SK하이닉스 현재가 + 등락률 (yfinance)."""
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
    """USD/KRW 환율 + 전일 대비 방향 (yfinance)."""
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
            "declining": change < 0,
        }
    except Exception as e:
        log(f"FX error: {e}")
        return None


def get_foreign_investor() -> dict | None:
    """외국인 코스피 순매수 — NAVER Finance 시간별 투자자 동향.

    URL: /sise/investorDealTrendTime.naver?bizdate=YYYYMMDD&sosok=01
    Table columns: 시간, 개인, 외국인, 기관계, [기관상세], 기타법인
    Values in 억원 (cumulative for the day).
    """
    trd_date = _trading_date()
    try:
        resp = requests.get(
            f"https://finance.naver.com/sise/investorDealTrendTime.naver"
            f"?bizdate={trd_date}&sosok=01",
            headers=NAVER_HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            log(f"NAVER investor: HTTP {resp.status_code}")
            return None

        text = resp.content.decode("euc-kr", errors="replace")
        soup = BeautifulSoup(text, "html.parser")

        table = soup.find("table", class_="type_1")
        if not table:
            log("NAVER investor: table not found")
            return None

        # First data row (latest time) has: 시간, 개인, 외국인, 기관, ...
        # Header row order: 시간, 개인, 외국인, 기관계, 금융투자, 보험, 투신, 은행, 기타금융, 연기금, 기타법인
        for row in table.find_all("tr"):
            tds = row.find_all("td")
            if len(tds) >= 3:
                time_str = tds[0].get_text(strip=True)
                if ":" in time_str:  # It's a time value like "17:13"
                    foreign_text = tds[2].get_text(strip=True)
                    foreign_val = _parse_number(foreign_text)  # 억원
                    log(f"외국인 {time_str}: {foreign_val:+,.0f}억원 (date={trd_date})")
                    return {
                        "net_eok": foreign_val,
                        "net": foreign_val * 1e8,
                        "is_buying": foreign_val > 0,
                        "time": time_str,
                        "date": trd_date,
                    }

        log(f"NAVER investor: no data rows for {trd_date}")
    except Exception as e:
        log(f"Foreign investor error: {e}")
    return None


def get_program_trading() -> dict | None:
    """프로그램 비차익 순매수 — NAVER Finance 시간별 프로그램 매매.

    URL: /sise/programDealTrendTime.naver?bizdate=YYYYMMDD&sosok=
    Table: 시간, 차익(매수,매도,순매수), 비차익(매수,매도,순매수), 전체(매수,매도,순매수)
    Values in 억원 (cumulative for the day).
    """
    trd_date = _trading_date()
    try:
        resp = requests.get(
            f"https://finance.naver.com/sise/programDealTrendTime.naver"
            f"?bizdate={trd_date}&sosok=",
            headers=NAVER_HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            log(f"NAVER program: HTTP {resp.status_code}")
            return None

        text = resp.content.decode("euc-kr", errors="replace")
        soup = BeautifulSoup(text, "html.parser")

        table = soup.find("table", class_="type_1")
        if not table:
            log("NAVER program: table not found")
            return None

        # Columns: 시간, 차익매수, 차익매도, 차익순매수, 비차익매수, 비차익매도, 비차익순매수, ...
        for row in table.find_all("tr"):
            tds = row.find_all("td")
            if len(tds) >= 7:
                time_str = tds[0].get_text(strip=True)
                if ":" in time_str:
                    nonarb_buy = _parse_number(tds[4].get_text(strip=True))
                    nonarb_sell = _parse_number(tds[5].get_text(strip=True))
                    nonarb_net = _parse_number(tds[6].get_text(strip=True))
                    log(f"비차익 {time_str}: 매수 {nonarb_buy:,.0f} 매도 {nonarb_sell:,.0f} 순매수 {nonarb_net:+,.0f}억원")
                    return {
                        "net_eok": nonarb_net,
                        "net": nonarb_net * 1e8,
                        "buy_eok": nonarb_buy,
                        "sell_eok": nonarb_sell,
                        "is_buying": nonarb_net > 0,
                        "time": time_str,
                        "date": trd_date,
                    }

        log(f"NAVER program: no data rows for {trd_date}")
    except Exception as e:
        log(f"Program trading error: {e}")
    return None


# ── Report Formatter ─────────────────────────────────────


def format_report(price, fx, foreign, program) -> str:
    now = datetime.now(KST).strftime("%m/%d %H:%M")
    lines = [f"*{TICKER_NAME} NXT 모니터링*", f"_{now} KST_", ""]

    if price and price["price"]:
        chg = f"{price['change_pct']:+.2f}%" if price["change_pct"] else ""
        lines.append(f"현재가: *{price['price']:,.0f}원* ({chg})")
        if price["high"] and price["low"]:
            lines.append(f"고/저: {price['high']:,.0f} / {price['low']:,.0f}")

    lines.append("")
    lines.append("*— 3박자 조건 —*")
    lines.append("")

    met = 0

    # ① 외국인 순매수 전환
    if foreign:
        ts = f" [{foreign['time']}]" if foreign.get("time") else ""
        if foreign["is_buying"]:
            c1 = "O"
            t1 = f"순매수 {foreign['net_eok']:+,.0f}억{ts}"
            met += 1
        else:
            c1 = "X"
            t1 = f"순매도 {foreign['net_eok']:,.0f}억{ts}"
    else:
        c1, t1 = "?", "데이터 미수신"
    lines.append(f"[{c1}] 외국인 매수: {t1}")

    # ② 프로그램 비차익 매수
    if program:
        ts = f" [{program['time']}]" if program.get("time") else ""
        if program["is_buying"]:
            c2 = "O"
            t2 = f"순매수 {program['net_eok']:+,.0f}억{ts}"
            met += 1
        else:
            c2 = "X"
            t2 = f"순매도 {program['net_eok']:,.0f}억{ts}"
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
    foreign = get_foreign_investor()
    program = get_program_trading()

    met = 0
    if foreign and foreign["is_buying"]:
        met += 1
    if program and program["is_buying"]:
        met += 1
    if fx and fx["declining"]:
        met += 1

    msg = format_report(price, fx, foreign, program)
    log(msg)

    if met >= 2:
        send_telegram(msg)
    else:
        log(f"{met}/3 충족 — Telegram 미발송")

    return 1 if met == 3 else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NXT 3박자 모니터링")
    parser.add_argument("--once", action="store_true", help="1회 체크 후 종료")
    args = parser.parse_args()

    sys.exit(run_once())
