# Multi-Agent Investment Advisory System

데이터 기반 멀티 에이전트 투자 방향성 자문 시스템.

## Architecture

4개 에이전트가 협업하여 투자 방향성을 도출:
- **investment-advisor** (Orchestrator): 전체 워크플로우 조율 + 종합 자문
- **info-collector**: yfinance + WebSearch로 금융/비금융 데이터 수집
- **data-processor**: 테마 분류, 감성 분석, 나비효과 체인 감지
- **db-agent**: 자연어→SQL 질의, 데이터 기반 답변 (SELECT only)

## Quick Start

```bash
# DB 초기화
python scripts/init_db.py

# 시장 데이터 수집 (주식 only, 90일)
python scripts/collect_market_data.py --asset-type stock --days 90

# 전체 수집 + 기술적 지표
python scripts/collect_market_data.py --days 90 --indicators

# FRED 매크로 데이터 수집 (전체, 3년)
FRED_API_KEY=xxx python scripts/collect_fred_data.py

# FRED 카테고리별 수집
FRED_API_KEY=xxx python scripts/collect_fred_data.py --category inflation --years 5

# FRED 매크로 대시보드 조회
python scripts/collect_fred_data.py --dashboard

# 시장 모니터링 (dry-run)
python scripts/run_monitor.py --dry-run

# 시장 모니터링 (텔레그램 전송)
TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy python scripts/run_monitor.py

# 테스트 실행
pytest tests/ -v
```

## Project Structure

```
src/
  utils/config.py          # 설정 (자산 목록, 임계값, DB 경로)
  collection/              # 데이터 수집 (yfinance, 뉴스)
  processing/              # 데이터 처리 (감성, 관련성, 나비효과)
  database/                # DB 레이어 (스키마, CRUD, 쿼리, NL→SQL)
  analysis/                # 분석 (트렌드, 리스크, 배분, 교차테마)
  monitoring/              # 시장 모니터링 + 텔레그램 알림
scripts/                   # CLI 도구
tests/                     # pytest 테스트
.claude/agents/            # 에이전트 정의
data/investment.db         # SQLite 데이터베이스
```

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
- `portfolio_trades`: 실매매 거래 기록 (매수/매도, 분할매수 회차, 전략명)
- `alert_log`: 알림 전송 이력 (중복 방지용 dedup_key)
- `macro_indicators`: FRED 매크로 경제 지표 시계열 (series_id + date)

## Journals & Reports

- `20260220_advisor.md`: 투자 자문 보고서 (실행 기록 포함)
- `journals/20260220_investment_journal.md`: 투자 일지 (분석→결정→실행)
- `journals/20260220_status.md`: 에이전트 핸드오프 문서 (미완료 작업 포함)

## Key Rules

- DB 에이전트는 **SELECT 쿼리만** 실행 가능
- 모든 투자 자문에 **면책 조항** 포함
- 뉴스 수집 시 `content_hash`로 중복 방지
- 기술적 지표는 `pandas_ta` 라이브러리 사용
- 감성 분석은 VADER + 금융 도메인 커스텀 사전

## Dependencies

`requirements.txt` 참조. 핵심: yfinance, pandas, pandas-ta, nltk, beautifulsoup4, requests

## FRED API

23개 시리즈 수집 (금리, 인플레이션, 고용, GDP, 금융환경, 주거, 심리, 통화).
환경변수: `FRED_API_KEY` (무료: https://fred.stlouisfed.org/docs/api/api_key.html)

## Market Monitor

자동 시장 모니터링 + 텔레그램 알림 시스템 (`src/monitoring/`).

9종 알림: RSI 과매도/과매수, 일일 가격 급변, MACD 크로스, 골든/데드 크로스, 볼린저 스퀴즈, 포트폴리오 P&L, 분할매수 트리거, 시간 트리거, 리스크 상승.

```bash
# Cron 등록 (하루 6회, 평일)
# 08:00 ET / 10:00 ET / 12:00 ET / 16:30 ET / 19:00 ET / 23:00 ET (매일)
crontab -e
0 8,10,12 * * 1-5 cd /data/claude/fin_advisor && python scripts/run_monitor.py
30 16 * * 1-5 cd /data/claude/fin_advisor && python scripts/run_monitor.py
0 19 * * 1-5 cd /data/claude/fin_advisor && python scripts/run_monitor.py
0 23 * * * cd /data/claude/fin_advisor && python scripts/run_monitor.py
```

환경변수: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
