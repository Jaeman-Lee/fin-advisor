#!/usr/bin/env python3
"""Telegram 양방향 투자 자문 봇 — Long Polling.

지원 명령어:
  포트폴리오 / /portfolio  — 전체 보유 P&L
  하이닉스 / /hynix        — SK하이닉스 현재 신호
  트리거 / /trigger        — 빅테크·PLTR 분할매수 트리거 상태
  /scan TICKER             — 특정 종목 가격·RSI·MACD 요약
  도움말 / /help           — 명령어 목록

보안: TELEGRAM_CHAT_ID와 일치하는 chat_id만 처리.
"""

import logging
import os
import sys
import time
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

import requests
import yfinance as yf
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from portfolio_config import (
    ALL_POSITIONS,
    POSITIONS,
    PLTR_TRANCHE_2_TRIGGERS,
    compute_pnl,
    check_tranche_2_triggers,
    check_tranche_3_triggers,
    check_price_drop_trigger,
    check_time_elapsed_trigger,
)
from monitor_hynix import (
    fetch_data as hynix_fetch,
    analyze as hynix_analyze,
    format_telegram_msg as hynix_format_msg,
)

# ── Config ───────────────────────────────────────────────────
KST = timezone(timedelta(hours=9))
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# 한국어 이름 → 티커 매핑
TICKER_ALIASES: dict[str, str] = {
    "하이닉스": "000660.KS",
    "sk하이닉스": "000660.KS",
    "삼성전자": "005930.KS",
    "한화리츠": "451800.KS",
    "카카오": "035720.KS",
    "네이버": "035420.KS",
    "셀트리온": "068270.KS",
    "솔라나": "SOL-USD",
    "비트코인": "BTC-USD",
    "이더리움": "ETH-USD",
}
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
AUTHORIZED_CHAT_ID = int(TELEGRAM_CHAT_ID) if TELEGRAM_CHAT_ID else None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Telegram API ─────────────────────────────────────────────

def send_message(chat_id: int, text: str) -> bool:
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=15,
        )
        return resp.status_code == 200
    except Exception as e:
        log.error(f"send_message error: {e}")
        return False


def get_updates(offset: int | None) -> list:
    params: dict = {"timeout": 30, "allowed_updates": ["message"]}
    if offset is not None:
        params["offset"] = offset
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
            params=params,
            timeout=40,
        )
        if resp.status_code == 200:
            return resp.json().get("result", [])
    except Exception as e:
        log.error(f"getUpdates error: {e}")
    return []


# ── Helpers ──────────────────────────────────────────────────

def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def fetch_closes(ticker: str, period: str = "3mo") -> pd.Series | None:
    try:
        data = yf.download(ticker, period=period, interval="1d", progress=False)
        if data is None or len(data) < 2:
            return None
        c = data["Close"]
        if isinstance(c, pd.DataFrame):
            c = c.iloc[:, 0]
        return c.dropna()
    except Exception:
        return None


def fetch_prices(tickers: list[str]) -> dict[str, float]:
    prices = {}
    for ticker in tickers:
        closes = fetch_closes(ticker, period="5d")
        if closes is not None and len(closes) > 0:
            prices[ticker] = float(closes.iloc[-1])
    return prices


def now_kst() -> str:
    return datetime.now(KST).strftime("%m/%d %H:%M")


# ── Command Handlers ─────────────────────────────────────────

def reply_help(chat_id: int):
    msg = (
        "*투자 자문 봇 명령어*\n\n"
        "`포트폴리오` / `/portfolio` — 전체 보유 P&L\n"
        "`하이닉스` / `/hynix` — SK하이닉스 현재 신호\n"
        "`트리거` / `/trigger` — 빅테크·PLTR 분할매수 트리거 상태\n"
        "`/scan TICKER` — 특정 종목 가격·RSI·MACD 요약\n"
        "`/ticker 회사명` — 티커 코드 검색 (예: `/ticker SK Hynix`)\n"
        "`도움말` / `/help` — 이 목록"
    )
    send_message(chat_id, msg)


def reply_portfolio(chat_id: int):
    send_message(chat_id, "포트폴리오 조회 중...")

    usd_positions = {t: p for t, p in ALL_POSITIONS.items() if p["currency"] == "USD"}
    prices = fetch_prices(list(usd_positions.keys()))

    if not prices:
        send_message(chat_id, "가격 조회 실패. 잠시 후 재시도해주세요.")
        return

    pnl_rows = compute_pnl(usd_positions, prices)
    lines = ["*보유현황 P&L (USD)*", f"_{now_kst()} KST_", ""]

    for row in pnl_rows:
        if row["ticker"] == "TOTAL":
            lines.append("─" * 28)
            lines.append(
                f"*합계*: ${row['market_value']:,.0f} "
                f"({row['pnl']:+,.0f}, {row['pnl_pct']:+.1f}%)"
            )
        else:
            price = prices.get(row["ticker"], 0)
            strategy = usd_positions[row["ticker"]].get("strategy", "")
            lines.append(
                f"*{row['ticker']}* {row['shares']}주 @${price:,.2f}\n"
                f"  P&L: ${row['pnl']:+,.0f} ({row['pnl_pct']:+.1f}%) [{strategy}]"
            )

    # KRW 자산 고정
    lines += [
        "",
        "*KRW 자산*",
        "한화리츠(451800): 18주 @5,350원 [리츠/배당]",
        "KRX 금: 18g @227,431원/g [안전자산]",
    ]

    send_message(chat_id, "\n".join(lines))


def reply_hynix(chat_id: int):
    send_message(chat_id, "SK하이닉스 분석 중...")
    daily, intra = hynix_fetch()
    if daily is None:
        send_message(chat_id, "SK하이닉스 데이터 조회 실패.")
        return
    r = hynix_analyze(daily, intra)
    send_message(chat_id, hynix_format_msg(r))


def reply_trigger(chat_id: int):
    send_message(chat_id, "트리거 상태 조회 중...")

    bigtech_tickers = list(POSITIONS.keys())
    all_tickers = bigtech_tickers + ["PLTR"]
    prices = fetch_prices(all_tickers)

    # RSI for bigtech
    rsi_values: dict[str, float | None] = {}
    for ticker in bigtech_tickers:
        closes = fetch_closes(ticker)
        if closes is not None and len(closes) > 14:
            rsi_values[ticker] = float(calc_rsi(closes).dropna().iloc[-1])
        else:
            rsi_values[ticker] = None

    t2 = check_tranche_2_triggers(prices, rsi_values)
    t3 = check_tranche_3_triggers()

    # PLTR 2차 트리거
    pltr_price = prices.get("PLTR")
    pltr_pos = {"PLTR": {"avg_price": 134.19, "shares": 6}}
    pltr_drop = check_price_drop_trigger(
        {"PLTR": pltr_price} if pltr_price else {},
        pltr_pos,
        PLTR_TRANCHE_2_TRIGGERS["price_drop_pct"],
    )
    pltr_time = check_time_elapsed_trigger(PLTR_TRANCHE_2_TRIGGERS["time_target"])

    pltr_rsi_val: float | None = None
    closes = fetch_closes("PLTR")
    if closes is not None and len(closes) > 14:
        pltr_rsi_val = float(calc_rsi(closes).dropna().iloc[-1])
    pltr_rsi_fired = (
        pltr_rsi_val is not None
        and pltr_rsi_val <= PLTR_TRANCHE_2_TRIGGERS["rsi_threshold"]
    )
    pltr_any = pltr_drop.fired or pltr_time.fired or pltr_rsi_fired

    def icon(fired) -> str:
        return "✅" if fired else ("⏳" if fired is False else "❓")

    lines = [
        "*분할매수 트리거 상태*",
        f"_{now_kst()} KST_",
        "",
        f"*빅테크 2차:* {'✅ FIRED' if t2.any_fired else '⏳ 대기'}",
    ]
    for tr in t2.triggers:
        lines.append(f"  {icon(tr.fired)} {tr.details}")

    lines += ["", f"*빅테크 3차:* {'✅ FIRED' if t3.any_fired else '⏳ 대기'}"]
    for tr in t3.triggers:
        lines.append(f"  {icon(tr.fired)} {tr.details}")

    rsi_detail = (
        f"RSI {pltr_rsi_val:.1f} (기준: ≤{PLTR_TRANCHE_2_TRIGGERS['rsi_threshold']})"
        if pltr_rsi_val is not None
        else "RSI N/A"
    )
    lines += [
        "",
        f"*PLTR 2차:* {'✅ FIRED' if pltr_any else '⏳ 대기'}",
        f"  {icon(pltr_drop.fired)} {pltr_drop.details}",
        f"  {icon(pltr_time.fired)} {pltr_time.details}",
        f"  {icon(pltr_rsi_fired)} {rsi_detail}",
    ]

    send_message(chat_id, "\n".join(lines))


def reply_ticker_search(chat_id: int, query: str):
    send_message(chat_id, f"'{query}' 검색 중...")
    try:
        results = yf.Search(query, max_results=8)
        quotes = [
            q for q in results.quotes
            if q.get("typeDisp") in ("equity", "etf", "fund", "index", "cryptocurrency")
        ][:6]
    except Exception as e:
        send_message(chat_id, f"검색 실패: {e}")
        return

    if not quotes:
        send_message(chat_id, f"'{query}'에 대한 검색 결과가 없습니다.")
        return

    type_emoji = {"equity": "📌", "etf": "📦", "index": "📊", "cryptocurrency": "🪙", "fund": "💼"}
    lines = [f"*'{query}' 검색 결과*\n"]
    for q in quotes:
        symbol = q.get("symbol", "")
        name = (q.get("shortname") or q.get("longname") or "").strip()
        exchange = q.get("exchDisp", "")
        type_ = q.get("typeDisp", "equity")
        emoji = type_emoji.get(type_, "📌")
        lines.append(f"{emoji} `{symbol}`  {name}  _{exchange}_")

    lines.append("\n사용법: `/scan 티커코드` (예: `/scan 000660.KS`)")
    send_message(chat_id, "\n".join(lines))


def reply_scan(chat_id: int, ticker: str):
    ticker = TICKER_ALIASES.get(ticker.lower(), ticker)
    send_message(chat_id, f"{ticker} 스캔 중...")
    closes = fetch_closes(ticker)
    if closes is None or len(closes) < 2:
        send_message(chat_id, f"{ticker} 데이터 조회 실패.")
        return

    price = float(closes.iloc[-1])
    prev = float(closes.iloc[-2])
    change_pct = (price - prev) / prev * 100

    rsi_val = float(calc_rsi(closes).dropna().iloc[-1]) if len(closes) > 14 else None
    sma20 = float(closes.rolling(20).mean().iloc[-1]) if len(closes) >= 20 else None
    sma50 = float(closes.rolling(50).mean().iloc[-1]) if len(closes) >= 50 else None

    macd_line = closes.ewm(span=12, adjust=False).mean() - closes.ewm(span=26, adjust=False).mean()
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_val = float(macd_line.iloc[-1])
    signal_val = float(signal_line.iloc[-1])
    macd_status = "골든크로스" if macd_val > signal_val else "데드크로스"

    # RSI 해석
    if rsi_val is None:
        rsi_str = "N/A"
        rsi_comment = ""
    elif rsi_val <= 30:
        rsi_str = f"{rsi_val:.1f}"
        rsi_comment = "과매도 — 많이 빠진 상태, 반등 가능성"
    elif rsi_val >= 70:
        rsi_str = f"{rsi_val:.1f}"
        rsi_comment = "과매수 — 많이 오른 상태, 조정 가능성"
    elif rsi_val <= 45:
        rsi_str = f"{rsi_val:.1f}"
        rsi_comment = "약세 구간"
    else:
        rsi_str = f"{rsi_val:.1f}"
        rsi_comment = "중립"

    # SMA 해석 (가격 vs 이동평균선)
    if sma20:
        sma20_str = f"{sma20:,.2f}"
        sma20_comment = "현재가 위 (단기 상승세)" if price > sma20 else "현재가 아래 (단기 하락세)"
    else:
        sma20_str = "N/A"
        sma20_comment = ""

    if sma50:
        sma50_str = f"{sma50:,.2f}"
        sma50_comment = "현재가 위 (중기 상승세)" if price > sma50 else "현재가 아래 (중기 하락세)"
    else:
        sma50_str = "N/A"
        sma50_comment = ""

    # MACD 해석
    macd_comment = "매수 신호 — 상승 모멘텀 시작" if macd_val > signal_val else "매도 신호 — 하락 모멘텀 진행 중"

    msg = (
        f"*{ticker} 스캔* ({now_kst()})\n"
        f"현재가: *{price:,.2f}* ({change_pct:+.2f}%)\n\n"
        f"📊 *RSI {rsi_str}* — 0~100 사이 과열 지표\n"
        f"  └ 30 이하=과매도, 70 이상=과매수\n"
        f"  └ 지금: {rsi_comment}\n\n"
        f"📈 *SMA20 {sma20_str}* — 20일 평균 주가\n"
        f"  └ 현재가가 평균보다 높으면 단기 강세\n"
        f"  └ 지금: {sma20_comment}\n\n"
        f"📉 *SMA50 {sma50_str}* — 50일 평균 주가\n"
        f"  └ 중기 추세 기준선\n"
        f"  └ 지금: {sma50_comment}\n\n"
        f"🔀 *MACD {macd_status}* — 추세 전환 신호\n"
        f"  └ 골든크로스=상승 전환, 데드크로스=하락 전환\n"
        f"  └ 지금: {macd_comment}"
    )
    send_message(chat_id, msg)


# ── Router ───────────────────────────────────────────────────

def handle_message(text: str, chat_id: int):
    if AUTHORIZED_CHAT_ID and chat_id != AUTHORIZED_CHAT_ID:
        log.warning(f"Unauthorized chat_id: {chat_id} — ignored")
        return

    lower = text.strip().lower()

    if lower in ("포트폴리오", "/portfolio"):
        reply_portfolio(chat_id)
    elif lower in ("하이닉스", "/hynix"):
        reply_hynix(chat_id)
    elif lower in ("트리거", "/trigger"):
        reply_trigger(chat_id)
    elif lower.startswith("/scan "):
        parts = text.strip().split(None, 1)
        ticker = parts[1].upper() if len(parts) > 1 else ""
        if ticker:
            reply_scan(chat_id, ticker)
        else:
            send_message(chat_id, "사용법: `/scan TICKER` (예: `/scan TSLA`)")
    elif lower.startswith("/ticker "):
        parts = text.strip().split(None, 1)
        query = parts[1] if len(parts) > 1 else ""
        if query:
            reply_ticker_search(chat_id, query)
        else:
            send_message(chat_id, "사용법: `/ticker 회사명` (예: `/ticker SK Hynix`)")
    else:
        reply_help(chat_id)


# ── Main Loop ────────────────────────────────────────────────

def main():
    if not TELEGRAM_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)

    log.info("Telegram bot started (long polling)")
    offset: int | None = None

    while True:
        updates = get_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1
            msg = update.get("message", {})
            text = msg.get("text", "")
            chat_id = msg.get("chat", {}).get("id")
            if text and chat_id:
                log.info(f"[{chat_id}] {text!r}")
                try:
                    handle_message(text, chat_id)
                except Exception as e:
                    log.error(f"Handler error: {e}")
                    send_message(chat_id, f"오류 발생: {e}")

        if not updates:
            time.sleep(1)


if __name__ == "__main__":
    main()
