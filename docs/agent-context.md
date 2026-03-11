# fin-advisor — Agent Context

## 프로젝트 목적
데이터 기반 개인 자산관리 + 투자 자문 통합 시스템.
시장 분석, 6-agent 토론 기반 종목 추천, 텔레그램 양방향 봇, 실시간 모니터링.

## 핵심 설계 원칙

1. **포트폴리오 단일 진실**: `scripts/portfolio_config.py`가 유일한 보유현황 소스
2. **6-agent 토론**: value/growth/momentum/income/macro/risk 전문가 독립 분석 → 투표
3. **트리거 기반 분할매수**: 감정 배제, 조건 충족 시 기계적 집행
4. **텔레그램 양방향**: `scripts/telegram_bot.py` — Long polling, AUTHORIZED_CHAT_ID 보안
5. **증권사 재직 제약**: 일 3회, 월 30회, 5일 보유 의무 항상 고려

## 현재 보유 포지션 (2026-03-11 기준)

### USD 주식
| 종목 | 주수 | 매입가 | 전략 |
|------|------|--------|------|
| GOOGL | 10주 | $305.16 | US빅테크과매도 (3차 대기) |
| AMZN | 19주 | $209.3873 | US빅테크과매도 (3차 대기) |
| MSFT | 10주 | $404.09 | US빅테크과매도 (3차 대기) |
| BRK-B | 6주 | $502.03 | 가치투자 |
| V | 2주 | $314.02 | 결제인프라 (2026-03-11 신규) |
| META | 1주 | $657.35 | AI광고플랫폼 (2026-03-11 신규) |

### KRW 자산
| 종목 | 수량 | 매입가 |
|------|------|--------|
| SK하이닉스(000660.KS) | 27주 | ₩991,000 — 손절선 ₩920,000 |
| KRX 금 | 18g | ₩227,431/g — 목표가 ₩260,000/g |

### 현금
- USD: $3,683.92
- KRW: ₩0 (3/20 월급 ₩200만 예정)

### 확정 손실 이력
| 종목 | 손실 |
|------|------|
| 진원생명과학 | -₩1,224,816 (-40.0%) |
| 카메코(CCJ) | -₩334,936 (-6.1%) |
| PLTR | -₩1,278,045 (-12.7%) |
| ACRE | -₩77,220 (-41.4%) |
| 한화리츠 | -₩6,300 (-6.5%) |
| **합계** | **-₩2,921,317** |

## 예정 액션

| 날짜 | 액션 | 내용 |
|------|------|------|
| 3/20(금) | 3차 트랜치 | GOOGL 2주 + AMZN 3주 + MSFT 1주 (~$1,663) |
| 3/20(금) | 월급 환전 | ₩200만 → USD (~$1,355) |

## 워치리스트

| 종목 | 진입 조건 |
|------|---------|
| VZ | RSI 60 이하 풀백 + MACD 반전 (현재 RSI 70.7 과매수) |
| JPM | RSI 40 이하 + MACD 골든크로스 전환 |
| NVDA | MACD 골든크로스 전환 (현재 데드) |
| TSM | MACD 골든크로스 + 지정학 안정 |
| PLTR | RSI 55 이하 조정 (현재 68.5 과열, 확정손실 이력) |
| BITX | RSI 40+ + MACD 골든 + BTC > SMA20 |
| SOL-USD | RSI 45+ + MACD 골든 + SEC 규제 완화 |

## 파일 구조 (핵심)

```
scripts/
  portfolio_config.py     ← 보유현황 단일 진실 (항상 최신 유지)
  telegram_bot.py         ← 양방향 텔레그램 봇 (Long polling)
  quick_scan.py           ← 장중 트리거 체크 + Telegram 알림
  daily_analysis.py       ← 일일 종합 리포트
  monitor_hynix.py        ← SK하이닉스 5분 모니터링
  monitor_nxt_conditions.py ← NXT 3박자 체크 (met>=2 시 발송)
  hynix_entry_monitor.py  ← 하이닉스 진입 모니터
  payday_alert.py         ← 월급일 알림 (매월 21일)
.claude/agents/           ← 6명 전략 에이전트 정의
Procfile                  ← Railway 배포 (worker: telegram_bot.py)
```

## 텔레그램 봇 명령어

| 명령어 | 동작 |
|--------|------|
| `포트폴리오` / `/portfolio` | 전체 보유 P&L |
| `하이닉스` / `/hynix` | SK하이닉스 신호 |
| `트리거` / `/trigger` | 분할매수 트리거 상태 |
| `/scan TICKER` | 종목 스캔 (한국어 설명 포함) |
| `/ticker 회사명` | 티커 코드 검색 |
| `도움말` / `/help` | 명령어 목록 |

## 주요 데이터 흐름

```
portfolio_config.py (보유현황)
  ↓
quick_scan.py / daily_analysis.py (분석)
  ↓
6-agent debate (투자 판단)
  ↓
telegram_bot.py (사용자 응답) / send_report.py (이메일)
```

## 알려진 엣지 케이스

- `yfinance` MultiIndex 컬럼: `if isinstance(c, pd.DataFrame): c = c.iloc[:,0]` 패턴 필수
- SHY: 2026-03-11 매수 미체결 → 포지션 없음 (현금 $4,969으로 복원됨)
- PLTR: 워치리스트 재진입 검토 중이나 거부권 유효 (RSI 과열 + 손실 이력)
- KRW=X: yfinance 환율 티커 (USD/KRW 직접 조회)
- 증권사 재직: 일 3회, 월 30회, 5일 보유 의무 — 매매 계획 시 항상 반영

## 개발 환경

- Python 3.11+, yfinance, pandas, pandas-ta, requests, beautifulsoup4
- SQLite: `data/investment.db`
- 환경변수: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `FRED_API_KEY`
- `.env` 파일 루트에 위치 (자동 로드)

## 세션 이력

| 날짜 | 주요 작업 |
|------|---------|
| 2026-02-20 | US빅테크과매도 1차 트랜치 (GOOGL 3+AMZN 4+MSFT 2) |
| 2026-02-25 | ACRE 손절, PLTR 1차 6주 매수 |
| 2026-02-26 | 이란-호르무즈 전쟁 발발, 포트폴리오 리스크 리뷰 |
| 2026-03-03 | 한화리츠 매도, BITX 워치리스트 추가 |
| 2026-03-05 | SK하이닉스 27주 신규 매수, KORU 매도 |
| 2026-03-06 | 2차 트랜치 집행 (GOOGL+AMZN+MSFT) |
| 2026-03-10 | PLTR 확정매도(-12.7%), 포트폴리오 정비, SHY 전략 수립 |
| 2026-03-11 | Telegram 봇 구현·배포, V 2주+META 1주 신규 매수, 포트폴리오 갱신 |
