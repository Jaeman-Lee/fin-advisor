#!/usr/bin/env python3
"""매월 21일(영업일) 급여 입금 알림 + 투자 집행 리마인더.

21일이 주말이면 직전 영업일에 발송.
Cron: 0 8 19-21 * * (매월 19~21일 08:00 KST)
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PAYDAY = 21
AMOUNT_KRW = 2_000_000


def get_payday(year: int, month: int) -> date:
    """21일이 주말이면 직전 금요일 반환."""
    d = date(year, month, PAYDAY)
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d -= timedelta(days=1)
    return d


def send_telegram(message: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("TELEGRAM credentials not set", file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }, timeout=10)
    return resp.ok


def main():
    today = date.today()
    payday = get_payday(today.year, today.month)

    if today != payday:
        print(f"Today {today} is not payday ({payday}). Skipping.")
        return

    dry_run = "--dry-run" in sys.argv

    msg = (
        f"<b>💰 급여일 알림</b>\n\n"
        f"오늘 <b>{AMOUNT_KRW:,}원</b> 입금 예정입니다.\n\n"
        f"<b>투자 집행 체크리스트:</b>\n"
        f"• KRW 잔고 확인\n"
        f"• 포트폴리오 현황 점검\n"
        f"• 환율 확인 (USD 전환 or KR 직접투자)\n"
        f"• 분할매수 트리거 상태 확인\n"
        f"• 관심종목 진입조건 확인\n\n"
        f"<i>투자 전 debate 실행 권장: python scripts/run_debate.py</i>"
    )

    if dry_run:
        print(msg)
        print("\n[DRY RUN — Telegram 미발송]")
    else:
        ok = send_telegram(msg)
        print(f"Telegram sent: {ok}")


if __name__ == "__main__":
    main()
