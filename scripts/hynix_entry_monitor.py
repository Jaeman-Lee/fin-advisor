#!/usr/bin/env python3
"""SK하이닉스 정규장 진입 모니터링 — 체크리스트 실시간 점검 + Telegram.

09:00~09:30 KST 1분 간격으로 체크리스트를 점검하고 Telegram 발송.
"""

import os
import sys
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# .env
_env = Path(__file__).resolve().parent.parent / ".env"
if _env.exists():
    for line in open(_env):
        line = line.strip()
        if line and not line.startswith("#"):
            line = line.removeprefix("export ")
            k, _, v = line.partition("=")
            if k and v:
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import yfinance as yf
import pandas as pd
from bs4 import BeautifulSoup

KST = timezone(timedelta(hours=9))
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── 토론 확정 매트릭스 ──
ENTRY_MATRIX = {
    "under_849": {"action": "HOLD", "desc": "매수 보류, 내일 재평가"},
    "850_900":   {"action": "BUY 2주", "desc": "최적 구간, 지정가 2주"},
    "900_950":   {"action": "BUY 1주", "desc": "1주만, 나머지 900K↓ 대기"},
    "over_950":  {"action": "WAIT", "desc": "전량 대기, 조정 후 재진입"},
}
STOP_FX = 1475.0      # 환율 한도
STOP_WAR = False       # 이란 확전 (수동)


def send_tg(msg: str):
    if not TG_TOKEN or not TG_CHAT:
        print("TG credentials missing")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception as e:
        print(f"TG error: {e}")


def get_nxt_hynix() -> dict | None:
    """넥스트레이드 실시간 SK하이닉스."""
    try:
        r = requests.post(
            "https://www.nextrade.co.kr/brdinfoTime/brdinfoTimeList.do",
            data={"rows": "20", "page": "1"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        for item in r.json().get("brdinfoTimeList", []):
            if item.get("isuSrdCd") == "A000660":
                return {
                    "price": int(item["curPrc"]),
                    "base": int(item["basePrc"]),
                    "open": int(item.get("oppr", 0)),
                    "high": int(item.get("hgpr", 0)),
                    "low": int(item.get("lwpr", 0)),
                    "rate": float(item.get("upDownRate", 0)),
                    "vol": int(item.get("accTdQty", 0)),
                    "time": item.get("nowTime", ""),
                }
    except Exception as e:
        print(f"NXT error: {e}")
    return None


def get_naver_hynix() -> dict | None:
    """NAVER 실시간 SK하이닉스 (정규장)."""
    try:
        r = requests.get(
            "https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:000660",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10,
        )
        item = r.json()["result"]["areas"][0]["datas"][0]
        return {
            "price": int(item["nv"]),
            "base": int(item["sv"]),
            "open": int(item.get("ov", 0)),
            "high": int(item.get("hv", 0)),
            "low": int(item.get("lv", 0)),
            "rate": float(item.get("cr", 0)),
            "vol": int(item.get("aq", 0)),
            "status": item.get("ms", ""),
        }
    except Exception as e:
        print(f"NAVER error: {e}")
    return None


def get_foreign_investor(date: str) -> str:
    """외국인 순매수 (NAVER)."""
    try:
        r = requests.get(
            f"https://finance.naver.com/sise/investorDealTrendTime.naver?bizdate={date}&sosok=01",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10,
        )
        soup = BeautifulSoup(r.content.decode("euc-kr", "replace"), "html.parser")
        table = soup.find("table", class_="type_1")
        if table:
            for row in table.find_all("tr"):
                tds = row.find_all("td")
                if len(tds) >= 3 and ":" in tds[0].get_text(strip=True):
                    return tds[2].get_text(strip=True)
    except:
        pass
    return "?"


_fx_cache = {"rate": 0.0, "chg": 0.0, "ts": 0}

def get_fx() -> tuple[float, float]:
    """USD/KRW 최신 + 변동률 (5분 캐시)."""
    now_ts = time.time()
    if _fx_cache["rate"] > 0 and now_ts - _fx_cache["ts"] < 300:
        return _fx_cache["rate"], _fx_cache["chg"]
    try:
        data = yf.download("KRW=X", period="5d", interval="1d", progress=False)
        c = data["Close"]
        if isinstance(c, pd.DataFrame):
            c = c.iloc[:, 0]
        vals = c.dropna()
        latest = float(vals.iloc[-1])
        prev = float(vals.iloc[-2])
        chg = (latest - prev) / prev * 100
        _fx_cache.update(rate=latest, chg=chg, ts=now_ts)
        return latest, chg
    except:
        return _fx_cache["rate"], _fx_cache["chg"]


def classify_price(price: int) -> dict:
    if price <= 849000:
        return ENTRY_MATRIX["under_849"]
    elif price <= 900000:
        return ENTRY_MATRIX["850_900"]
    elif price <= 950000:
        return ENTRY_MATRIX["900_950"]
    else:
        return ENTRY_MATRIX["over_950"]


def build_report(now: datetime) -> str:
    ts = now.strftime("%H:%M")
    today = now.strftime("%Y%m%d")

    # 가격 데이터 (NXT + NAVER 둘 다)
    nxt = get_nxt_hynix()
    naver = get_naver_hynix()

    # 정규장 열렸으면 NAVER 우선, 아니면 NXT
    if naver and naver.get("status") in ("OPEN", "CLOSE"):
        src = naver
        src_name = "정규장"
    elif naver and naver["vol"] > 0 and naver["price"] != naver["base"]:
        src = naver
        src_name = "정규장"
    elif nxt and nxt["price"] > 0:
        src = nxt
        src_name = "NXT"
    else:
        src = None
        src_name = "?"

    lines = [f"*SK하이닉스 진입 모니터*", f"_{ts} KST_", ""]

    # ① 현재가
    if src:
        p = src["price"]
        lines.append(f"현재가 ({src_name}): *{p:,}원* ({src['rate']:+.2f}%)")
        if src.get("open"):
            lines.append(f"시가: {src['open']:,} 고: {src['high']:,} 저: {src['low']:,}")
        lines.append(f"거래량: {src['vol']:,}")
    else:
        p = 0
        lines.append("현재가: 데이터 없음")

    # NXT도 같이 표시 (정규장과 다를 때)
    if nxt and src_name != "NXT" and nxt["price"] > 0:
        lines.append(f"NXT: {nxt['price']:,}원 ({nxt['rate']:+.2f}%)")

    lines.append("")

    # ② 5분봉 체크 (09:05 이후)
    if now.hour == 9 and now.minute >= 5 and src and src.get("open"):
        candle = "양봉" if src["price"] >= src["open"] else "음봉"
        diff = src["price"] - src["open"]
        lines.append(f"5분봉: *{candle}* ({diff:+,}원)")
    elif now.hour >= 9 and now.minute >= 5 and src and src.get("open"):
        candle = "양봉" if src["price"] >= src["open"] else "음봉"
        diff = src["price"] - src["open"]
        lines.append(f"캔들: *{candle}* (시가대비 {diff:+,}원)")
    else:
        lines.append("5분봉: 09:05 대기중")

    lines.append("")
    lines.append("*— 체크리스트 —*")
    lines.append("")

    # ③ 매수 구간 판정
    if p > 0:
        zone = classify_price(p)
        lines.append(f"[{'O' if 'BUY' in zone['action'] else 'X'}] 매수구간: *{zone['action']}* ({zone['desc']})")
    else:
        lines.append("[?] 매수구간: 가격 미확인")

    # ④ 외국인 순매수
    foreign_today = get_foreign_investor(today)
    foreign_prev = get_foreign_investor(
        (now - timedelta(days=1 if now.weekday() > 0 else 3)).strftime("%Y%m%d")
    )
    is_buying = False
    try:
        fval = int(foreign_today.replace(",", "").replace("+", ""))
        is_buying = fval > 0
    except:
        pass
    lines.append(f"[{'O' if is_buying else '?' if foreign_today == '?' else 'X'}] 외국인: {foreign_today}억 (전일: {foreign_prev}억)")

    # ⑤ 환율
    fx_rate, fx_chg = get_fx()
    fx_ok = 0 < fx_rate < STOP_FX
    if fx_rate > 0:
        lines.append(f"[{'O' if fx_ok else 'X'}] 환율: {fx_rate:,.1f}원 ({fx_chg:+.2f}%) {'< 1,475 OK' if fx_ok else '>= 1,475 경고'}")
    else:
        lines.append("[?] 환율: 미확인")

    # ⑥ 이란 확전
    lines.append(f"[O] 이란확전: 미감지 (수동확인)")

    # ⑦ 시장가 금지
    lines.append(f"[O] 시장가금지: 지정가만")

    lines.append("")

    # 종합 판정
    if p > 0:
        zone = classify_price(p)
        if "BUY" in zone["action"] and fx_ok:
            lines.append(f">> *{zone['action']}* 조건 충족!")
            if now.hour == 9 and now.minute < 5:
                lines.append(">> 09:05 5분봉 확인 후 진입")
        elif "WAIT" in zone["action"] or "HOLD" in zone["action"]:
            lines.append(f">> {zone['action']} — 대기")
        elif not fx_ok and fx_rate > 0:
            lines.append(">> 환율 경고 — 매수 보류")
        else:
            lines.append(">> 조건 미충족 — 대기")

    return "\n".join(lines)


def main():
    print("SK하이닉스 진입 모니터 시작 (09:00~09:30, 1분 간격)", flush=True)

    # 환율 미리 캐시
    get_fx()

    while True:
        now = datetime.now(KST)

        # 09:30 이후 종료
        if now.hour > 9 or (now.hour == 9 and now.minute > 30):
            print("09:30 경과, 모니터 종료", flush=True)
            msg = build_report(now)
            msg += "\n\n_모니터링 종료 (09:30)_"
            send_tg(msg)
            print(msg, flush=True)
            break

        # 리포트 생성 + 발송
        try:
            msg = build_report(now)
            print(f"\n{'='*50}", flush=True)
            print(msg, flush=True)
            send_tg(msg)
        except Exception as e:
            print(f"ERROR: {e}", flush=True)

        # 1분 대기
        elapsed = (datetime.now(KST) - now).total_seconds()
        wait = max(60 - elapsed, 5)
        time.sleep(wait)


if __name__ == "__main__":
    main()
