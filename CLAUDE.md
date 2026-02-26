# Personal Finance & Investment Platform

데이터 기반 **개인 자산관리 + 투자 자문** 통합 시스템.

시장 분석과 종목 추천뿐 아니라, 사용자의 전체 자산을 추적·관리하고
최적의 포트폴리오를 설계·유지하는 엔드투엔드 서비스를 제공한다.

## 3 Core Services

```
┌─────────────────────────────────────────────────────────────┐
│                    Personal Finance Platform                 │
├───────────────────┬──────────────────┬──────────────────────┤
│  1. 자산관리       │  2. 투자 자문     │  3. 시장 모니터링     │
│  Asset Management │  Advisory        │  Monitoring          │
├───────────────────┼──────────────────┼──────────────────────┤
│ • 전체 보유현황    │ • 종목 리서치     │ • 실시간 알림        │
│ • 멀티자산 P&L    │ • 매수/매도 전략  │ • 기술적 지표 감시   │
│ • 자산배분 분석    │ • 포트폴리오 설계 │ • 리스크 경고        │
│ • 실현손익 추적    │ • 분할매수 실행   │ • 글로벌 스캔        │
│ • 리밸런싱 제안    │ • 관심종목 평가   │ • 매크로 대시보드    │
│ • 환율/통화 관리   │ • 나비효과 체인   │ • 텔레그램/이메일    │
└───────────────────┴──────────────────┴──────────────────────┘
```

## Architecture

### Infrastructure Agents (데이터 레이어)
- **info-collector**: yfinance + WebSearch로 금융/비금융 데이터 수집
- **data-processor**: 테마 분류, 감성 분석, 나비효과 체인 감지
- **db-agent**: 자연어→SQL 질의, 데이터 기반 답변 (SELECT only)

### Strategy Debate Agents (의사결정 레이어)
6명의 전략 전문가가 토론하여 투자 판단:

| Agent | 관점 | 핵심 지표 |
|-------|------|----------|
| **value-investor** | 내재가치, 저평가 | P/E, P/B, FCF, 안전마진 |
| **growth-investor** | 성장성, 혁신 | 매출성장률, PEG, 매출총이익률 |
| **momentum-trader** | 추세, 기술적 | RSI, MACD, SMA, 볼린저 |
| **income-investor** | 배당, 현금흐름 | 배당수익률, 배당성향, FCF |
| **macro-strategist** | 거시경제 | 금리, 수익률곡선, VIX |
| **risk-manager** | 리스크 관리 (**거부권**) | 낙폭, 집중도, 변동성, 손실이력 |

### Orchestration
- **debate-moderator**: 토론 주재, 투표 집계, 최종 제안 도출
- **investment-advisor**: 전체 워크플로우 조율 + 종합 자문

### 토론 → 의사결정 흐름
```
데이터 수집 → 6명 독립 분석 → 교차 검증 → 투표
  → 만장일치: 자동 기록 + 이메일
  → 다수결: 이메일 제안
  → 분열/거부권: 텔레그램으로 사용자에게 판단 요청
```

```bash
# 토론 실행
python scripts/run_debate.py                    # 전체 포트폴리오
python scripts/run_debate.py --ticker GOOGL     # 단일 종목
python scripts/run_debate.py --dry-run          # 텔레그램 미발송
```

## Quick Start

```bash
# DB 초기화
python scripts/init_db.py

# 시장 데이터 수집 + 기술적 지표
python scripts/collect_market_data.py --days 90 --indicators

# FRED 매크로 데이터 수집
FRED_API_KEY=xxx python scripts/collect_fred_data.py

# 일일 분석 리포트 (포트폴리오 + 시장 + 관심종목)
python scripts/daily_analysis.py

# 글로벌 스캔 (장중 실시간)
python scripts/global_scan.py

# 시장 모니터링 + 텔레그램
TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy python scripts/run_monitor.py

# 한국 시장 분석
python scripts/analyze_kr_market.py

# 테스트
pytest tests/ -v
```

## Project Structure

```
src/
  utils/config.py          # 설정 (자산 목록, 임계값, DB 경로)
  collection/              # 데이터 수집 (yfinance, 뉴스, FRED)
  processing/              # 데이터 처리 (감성, 관련성, 나비효과)
  database/                # DB 레이어 (스키마, CRUD, 쿼리, NL→SQL)
  analysis/                # 분석 (트렌드, 리스크, 배분, 교차테마)
  monitoring/              # 시장 모니터링 + 텔레그램 알림
scripts/
  portfolio_config.py      # 전체 보유자산 + 전략 + 트리거 설정
  daily_analysis.py        # 일일 분석 리포트 (Track B)
  quick_scan.py            # 장중 빠른 스캔 (Track A)
  global_scan.py           # 글로벌 마켓 스캔
  analyze_kr_market.py     # 한국 시장 독립 분석
  run_monitor.py           # 모니터링 + 알림 배치
  send_report.py           # 이메일 발송
tests/                     # pytest 테스트 (116개)
journals/                  # 분석 리포트, 보유현황, 투자 일지
.claude/agents/            # 에이전트 정의
data/investment.db         # SQLite 데이터베이스
```

---

## Service 1: Asset Management (자산관리)

### 현재 보유 자산

`portfolio_config.py`에 정의. 사용자가 변경 사항 전달 시 갱신.

| 구분 | 종목 | 전략 |
|------|------|------|
| US 주식 | GOOGL, AMZN, MSFT | US빅테크과매도 (분할매수) |
| US 주식 | BRK-B | 가치투자 |
| US 주식 | ACRE | 인컴/배당 |
| KR 주식 | 한화리츠 (451800.KS) | 리츠/배당 |
| 원자재 | KRX 금 18g | 안전자산 |
| 현금 | USD + KRW | |

### 확정 손실 이력

| 종목 | 실현손익 |
|------|---------|
| 진원생명과학 | -1,224,816원 (-40.0%) |
| 카메코 (CCJ) | -334,936원 (-6.1%) |
| 팔란티어 (PLTR) | -1,278,045원 (-12.7%) |
| **합계** | **-2,837,797원** |

### Config 구조

```python
# portfolio_config.py
ALL_POSITIONS      # 전체 보유 자산 (US/KR 주식)
POSITIONS          # 분할매수 전략 대상 (GOOGL/AMZN/MSFT)
GOLD_POSITION      # 금 보유량 + 매입가
CASH_BALANCES      # USD/KRW 현금 잔고
WATCHLIST          # 관심종목 (미보유, 모니터링+진입조건 평가)
```

### 자산관리 시스템 로드맵

**Phase 1: 데이터 통합** (완료)
- `portfolio_config.py`에 전체 자산 정의
- 보유현황 저널 스냅샷 (`journals/YYYYMMDD_portfolio_holdings.md`)

**Phase 2: 통합 P&L 대시보드**
- `scripts/portfolio_dashboard.py` — 전체 자산 현재가 + P&L 집계
- 자산군별/전략별/통화별 집계, 터미널+마크다운+JSON 출력
- 이메일 리포트에 전체 포트폴리오 섹션 통합

**Phase 3: DB 기반 자산 추적**
- `portfolio_holdings` 테이블 — 날짜별 스냅샷
- `portfolio_trades` 확장 — KR 주식/금 거래 기록
- 시계열 P&L + 일별/주별/월별 수익률 분석
- 실현손익 DB 저장 + 누적 추적

**Phase 4: 자동화 + 인텔리전스**
- 자산배분 임계값 초과 시 리밸런싱 알림
- 종목별 손절/익절 자동 트리거
- 환율 변동 → KRW 환산 자산가치 모니터링
- 포트폴리오 최적화 제안 (리스크 대비 수익률)

---

## Service 2: Investment Advisory (투자 자문)

### 종목 리서치 + 전략

- **종목 분석**: yfinance + WebSearch로 기술적/펀더멘탈 분석
- **매수/매도 판단**: RSI, MACD, SMA, 볼린저밴드 + 감성분석 종합
- **분할매수 전략**: 트랜치별 트리거 (가격/시간/기술적 조건)
- **나비효과 체인**: 이벤트 인과관계 추적 → 파급 영향 예측

### 관심종목 (Watchlist)

`portfolio_config.py`의 `WATCHLIST` — 미보유 종목의 진입 조건 자동 평가.
현재: SOL-USD (Solana)

Daily Analysis + Global Scan에서 자동 추적.

### 분할매수 트리거 (US빅테크과매도)

| 트랜치 | 조건 (어느 하나 충족 시) |
|--------|------------------------|
| 2차 | 5% 하락 OR 2주 경과(3/6) OR RSI 45 회복 |
| 3차 | MACD 골든크로스 OR 4주 경과(3/20) OR SMA20 탈환 |

### 한국 시장 분석

독립형 스크립트 (`scripts/analyze_kr_market.py`): KOSPI/KOSDAQ 9개 섹션 분석.

### 보고서 구조

투자 자문 보고서, 종목 리서치, 보유현황 스냅샷은 `journals/` 디렉토리에 날짜별 저장.

---

## Service 3: Market Monitoring (시장 모니터링)

`src/monitoring/` + 3개 배치 스크립트.

### 알림 채널
- **텔레그램**: 실시간 알림 (9종)
- **이메일**: 정기 리포트 (GitHub Actions)

### 9종 알림

| 카테고리 | 트리거 | 우선순위 |
|----------|--------|:--------:|
| RSI 과매도/과매수 | RSI ≤ 30 or ≥ 70 | WARNING |
| 일일 가격 급변 | ≥ 3% (5% CRITICAL) | WARNING/CRITICAL |
| MACD 크로스 | 강세/약세 교차 | INFO/WARNING |
| 골든/데드 크로스 | SMA50 vs SMA200 | INFO/WARNING |
| 볼린저 스퀴즈 | 밴드폭 < 0.05 | INFO |
| 포트폴리오 P&L | -5% 손실 or +10% 이익 | CRITICAL/INFO |
| 분할매수 트리거 | 2차/3차 조건 충족 | CRITICAL |
| 시간 트리거 | 기한 도래 | CRITICAL |
| 리스크 상승 | risk score ≥ 0.7 | WARNING |

### 배치 스케줄

| 배치 | 주기 | 내용 |
|------|------|------|
| daily_analysis | KST 07:00 | 포트폴리오 P&L + 시장 분석 + 관심종목 |
| quick_scan | KST 0/2/4/6시 | 장중 빠른 가격/트리거 체크 |
| global_scan | KST 12/18시 | 글로벌 선물/VIX/아시아/환율 |
| run_monitor | 평일 6회 | 텔레그램 알림 9종 |

```bash
# Cron 등록
0 8,10,12 * * 1-5 cd /data/claude/fin_advisor && python scripts/run_monitor.py
30 16 * * 1-5 cd /data/claude/fin_advisor && python scripts/run_monitor.py
0 19 * * 1-5 cd /data/claude/fin_advisor && python scripts/run_monitor.py
0 23 * * * cd /data/claude/fin_advisor && python scripts/run_monitor.py
```

환경변수: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

---

## Database

SQLite DB with 13 tables:
- `asset_registry`: 추적 자산 마스터 (주식/채권/원자재/암호화폐/FX)
- `market_data`: OHLCV + 기술적 지표 (RSI, MACD, Bollinger, SMA)
- `raw_data_items`: 수집된 원본 데이터
- `processed_data`: 정제된 데이터 (감성점수, 관련성, 영향도)
- `themes`: 테마 분류 (macro, geopolitics, sector, asset, sentiment, technical)
- `butterfly_chains` / `butterfly_chain_links`: 나비효과 인과 체인
- `investment_signals`: 투자 시그널 (buy/sell/hold)
- `advisory_reports`: 자문 보고서 이력
- `data_sources`: 데이터 소스 추적
- `portfolio_trades`: 실매매 거래 기록
- `alert_log`: 알림 전송 이력
- `macro_indicators`: FRED 매크로 경제 지표 시계열

## Key Rules

- DB 에이전트는 **SELECT 쿼리만** 실행 가능
- 모든 투자 자문에 **면책 조항** 포함
- 뉴스 수집 시 `content_hash`로 중복 방지
- 기술적 지표는 `pandas_ta` 라이브러리 사용
- 감성 분석은 VADER + 금융 도메인 커스텀 사전
- 보유현황 변경은 사용자 확인 후에만 갱신

## Dependencies

`requirements.txt` 참조. 핵심: yfinance, pandas, pandas-ta, nltk, beautifulsoup4, requests

## FRED API

23개 시리즈 (금리, 인플레이션, 고용, GDP, 금융환경, 주거, 심리, 통화).
환경변수: `FRED_API_KEY`
