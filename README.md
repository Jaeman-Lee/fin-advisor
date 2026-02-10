# 멀티 에이전트 투자 자문 시스템

데이터 기반 멀티 에이전트 투자 방향성 자문 시스템입니다. 주식, 채권, 원자재, 암호화폐, FX 등 전 자산군에 대해 데이터를 수집하고, 정제/분석하여 포트폴리오 배분 전략을 도출합니다.

---

## 목차

- [시스템 구조](#시스템-구조)
- [설치 및 초기 설정](#설치-및-초기-설정)
- [전체 파이프라인 실행](#전체-파이프라인-실행)
- [단위 작업별 사용법](#단위-작업별-사용법)
  - [1. 데이터베이스 초기화](#1-데이터베이스-초기화)
  - [2. 시장 데이터 수집](#2-시장-데이터-수집)
  - [3. 기술적 지표 계산](#3-기술적-지표-계산)
  - [4. 뉴스 데이터 수집 및 저장](#4-뉴스-데이터-수집-및-저장)
  - [5. 데이터 처리 파이프라인](#5-데이터-처리-파이프라인)
  - [6. 데이터 조회 (DB 에이전트)](#6-데이터-조회-db-에이전트)
  - [7. 분석 모듈](#7-분석-모듈)
  - [8. 포트폴리오 배분 생성](#8-포트폴리오-배분-생성)
- [에이전트 사용법](#에이전트-사용법)
- [테스트](#테스트)
  - [전체 테스트 실행](#전체-테스트-실행)
  - [개별 테스트 모듈](#개별-테스트-모듈)
- [데이터베이스 스키마](#데이터베이스-스키마)
- [설정 커스터마이징](#설정-커스터마이징)
- [프로젝트 구조](#프로젝트-구조)

---

## 시스템 구조

```
사용자 질의
   │
   ▼
┌──────────────────────┐
│  investment-advisor   │  ← 메인 오케스트레이터
│  (종합 판단 + 자문)    │
└──────┬───────────────┘
       │
       ├──→ info-collector      (데이터 수집: yfinance + WebSearch)
       │         │
       │         ▼
       │    raw_data_items + market_data (DB 저장)
       │
       ├──→ data-processor      (데이터 정제 + 시그널 생성)
       │         │
       │         ▼
       │    processed_data + butterfly_chains + investment_signals
       │
       └──→ db-agent            (자연어 → SQL 질의)
                 │
                 ▼
            데이터 기반 답변 → 투자 방향성 도출
```

| 에이전트 | 역할 | 핵심 도구 |
|----------|------|-----------|
| `investment-advisor` | 메인 오케스트레이터, 종합 자문 | 하위 에이전트 조율, 분석 모듈 |
| `info-collector` | 시장 데이터 + 뉴스 수집 | yfinance, WebSearch |
| `data-processor` | 테마 분류, 감성 분석, 나비효과 체인 | VADER, 키워드 매칭 |
| `db-agent` | 자연어 질의 → SQL 실행 (읽기 전용) | NL-to-SQL, 분석 쿼리 |

---

## 설치 및 초기 설정

### 1단계: 의존성 설치

```bash
pip install -r requirements.txt
```

주요 라이브러리:
| 패키지 | 용도 |
|--------|------|
| `yfinance` | 주식/채권/원자재/암호화폐 시장 데이터 |
| `pandas` | 데이터프레임 처리 |
| `pandas-ta` | 기술적 지표 계산 (RSI, MACD, BB, SMA) |
| `nltk` | VADER 감성 분석 |
| `beautifulsoup4` | HTML 파싱 |
| `pytest` | 테스트 |

### 2단계: 데이터베이스 초기화

```bash
python scripts/init_db.py
```

출력 예시:
```
Initializing database at: /data/claude/fin_advisor/data/investment.db
Database created successfully
Tables created (11):
  - advisory_reports (0 rows)
  - asset_registry (0 rows)
  - butterfly_chain_links (0 rows)
  - butterfly_chains (0 rows)
  - data_sources (3 rows)        ← yfinance, websearch, manual
  - investment_signals (0 rows)
  - market_data (0 rows)
  - processed_data (0 rows)
  - raw_data_items (0 rows)
  - sqlite_sequence (2 rows)
  - themes (18 rows)             ← 6개 카테고리 × 3개 테마
```

### 3단계: 시장 데이터 수집

```bash
# 전체 자산 수집 (90일) + 기술적 지표 계산
python scripts/collect_market_data.py --days 90 --indicators
```

---

## 전체 파이프라인 실행

처음부터 끝까지 한 번에 실행하려면:

```bash
# 1. DB 초기화
python scripts/init_db.py

# 2. 시장 데이터 수집 + 기술적 지표
python scripts/collect_market_data.py --days 90 --indicators

# 3. 데이터 처리 파이프라인 (수집된 뉴스가 있는 경우)
python -c "
import sys; sys.path.insert(0, '.')
from src.database.operations import DatabaseOperations
from src.processing.deduplicator import deduplicate_unprocessed
from src.processing.categorizer import categorize_unprocessed
from src.processing.sentiment_scorer import score_items
from src.processing.relevance_scorer import score_and_filter, compute_impact_score
from src.processing.butterfly_chain import store_detected_chains

db = DatabaseOperations()
deduplicate_unprocessed(db)
categories = categorize_unprocessed(db)
items = db.get_unprocessed_items()
scored = score_items(items)
relevant = score_and_filter(scored, min_relevance=0.3)
for item in relevant:
    impact = compute_impact_score(item['sentiment_score'], item['relevance_score'])
    theme_info = categories.get(item['id'], {})
    proc_id = db.insert_processed_data(
        raw_item_id=item['id'], title=item['title'],
        theme_id=theme_info.get('theme_id'),
        summary=(item.get('content', '') or '')[:500],
        sentiment_score=item['sentiment_score'],
        sentiment_label=item['sentiment_label'],
        relevance_score=item['relevance_score'],
        impact_score=impact,
        affected_assets=item.get('affected_assets', []),
    )
    db.mark_as_processed(item['id'])
    store_detected_chains(db, item['title'] + ' ' + (item.get('content','') or ''), evidence_id=proc_id)
print(f'처리 완료: {len(relevant)}건')
"

# 4. 포트폴리오 배분 생성
python -c "
import sys; sys.path.insert(0, '.')
from src.database.operations import DatabaseOperations
from src.analysis.allocation_engine import generate_allocation, store_allocation_as_report
import json

db = DatabaseOperations()
result = generate_allocation(db, risk_tolerance='moderate')
store_allocation_as_report(db, result)
print(json.dumps(result['allocation'], indent=2, ensure_ascii=False))
"
```

---

## 단위 작업별 사용법

### 1. 데이터베이스 초기화

```bash
# 최초 생성
python scripts/init_db.py

# DB 리셋 (모든 데이터 삭제 후 재생성)
python -c "
import sys; sys.path.insert(0, '.')
from src.database.schema import reset_db
reset_db()
print('DB 리셋 완료')
"
```

### 2. 시장 데이터 수집

`scripts/collect_market_data.py`는 다양한 옵션을 지원합니다:

```bash
# 전체 자산 수집 (기본 365일)
python scripts/collect_market_data.py

# 특정 자산 유형만 수집
python scripts/collect_market_data.py --asset-type stock    # 주식만
python scripts/collect_market_data.py --asset-type bond     # 채권만
python scripts/collect_market_data.py --asset-type commodity # 원자재만
python scripts/collect_market_data.py --asset-type crypto   # 암호화폐만

# 특정 티커만 수집
python scripts/collect_market_data.py --tickers AAPL MSFT NVDA --days 30

# 수집 + 기술적 지표 계산
python scripts/collect_market_data.py --tickers AAPL BTC-USD GC=F --days 90 --indicators

# 기간 지정
python scripts/collect_market_data.py --days 180  # 최근 180일
```

**지원 티커 목록** (`src/utils/config.py`에서 관리):

| 자산 유형 | 티커 예시 |
|-----------|-----------|
| 주식 | `^GSPC`, `^IXIC`, `^DJI`, `AAPL`, `MSFT`, `NVDA`, `TSLA`, `005930.KS` |
| 채권 | `^TNX`(10Y), `^TYX`(30Y), `^FVX`(5Y), `^IRX`(3M), `TLT`, `SHY` |
| 원자재 | `GC=F`(금), `SI=F`(은), `CL=F`(WTI), `BZ=F`(브렌트), `NG=F`(천연가스) |
| 암호화폐 | `BTC-USD`, `ETH-USD`, `SOL-USD`, `XRP-USD`, `ADA-USD` |
| FX | `EURUSD=X`, `USDJPY=X`, `USDKRW=X`, `DX-Y.NYB`(달러인덱스) |

### 3. 기술적 지표 계산

시장 데이터 수집 후 별도로 기술적 지표를 계산할 수 있습니다:

```python
import sys; sys.path.insert(0, '.')
from src.database.operations import DatabaseOperations
from src.collection.technical_indicators import update_indicators_in_db

db = DatabaseOperations()

# 특정 자산의 지표 계산
asset_id = db.get_asset_id("AAPL")
count = update_indicators_in_db(db, asset_id)
print(f"{count}개 행 업데이트")

# 전체 자산의 지표 계산
for asset in db.get_all_assets():
    update_indicators_in_db(db, asset["id"])
```

**계산되는 지표:**
| 지표 | 설명 | 기본 설정 |
|------|------|-----------|
| SMA | 단순이동평균 | 20일, 50일, 200일 |
| RSI | 상대강도지수 | 14일 |
| MACD | 이동평균수렴확산 | 12/26/9 |
| Bollinger Bands | 볼린저 밴드 | 20일, 2σ |

### 4. 뉴스 데이터 수집 및 저장

뉴스 데이터는 `news_collector` 모듈로 구조화하여 저장합니다:

```python
import sys; sys.path.insert(0, '.')
from src.collection.news_collector import structure_search_result, store_news_items
from src.database.operations import DatabaseOperations

db = DatabaseOperations()

# 검색 결과를 구조화
items = [
    structure_search_result({
        "title": "Fed holds rates steady amid inflation concerns",
        "snippet": "The Federal Reserve kept interest rates unchanged...",
        "url": "https://example.com/article1",
    }),
    structure_search_result({
        "title": "NVIDIA reports record AI chip revenue",
        "snippet": "NVIDIA's data center revenue surged 120%...",
        "url": "https://example.com/article2",
    }),
]

# DB에 저장 (중복 자동 체크)
stored_ids = store_news_items(db, items)
print(f"저장된 항목: {len(stored_ids)}건")
```

**테마별 검색 쿼리 목록 조회:**

```python
from src.collection.news_collector import get_search_queries

# 전체 테마 쿼리
all_queries = get_search_queries()

# 특정 테마만
macro_queries = get_search_queries(["macro", "geopolitics"])
```

### 5. 데이터 처리 파이프라인

수집된 원시 데이터를 정제하는 5단계 파이프라인:

#### 5-1. 중복 제거

```python
from src.processing.deduplicator import deduplicate_unprocessed
from src.database.operations import DatabaseOperations

db = DatabaseOperations()
removed = deduplicate_unprocessed(db, threshold=0.85)
print(f"중복 제거: {removed}건")
```

#### 5-2. 테마 분류

```python
from src.processing.categorizer import categorize_item, get_best_theme

# 단일 항목 분류
matches = categorize_item(db, "Federal Reserve raises interest rate by 25bps")
# → [{'theme_id': 1, 'category': 'macro', 'name': 'Interest Rates', 'score': 1.0}, ...]

# 최적 테마 1개만
best = get_best_theme(db, "NVIDIA GPU demand surges amid AI boom")
# → {'theme_id': 8, 'category': 'sector', 'name': 'AI & Semiconductors', 'score': 0.67}

# 미처리 항목 일괄 분류
from src.processing.categorizer import categorize_unprocessed
categories = categorize_unprocessed(db)
# → {raw_item_id: {theme_id, category, name, score}, ...}
```

**테마 카테고리 (6개):**
| 카테고리 | 설명 | 예시 테마 |
|----------|------|-----------|
| `macro` | 거시경제 | 금리, 인플레이션, GDP |
| `geopolitics` | 지정학 | 미중관계, 중동, 러-우 |
| `sector` | 섹터 | AI/반도체, 에너지, 바이오 |
| `asset` | 자산 | 주식, 채권, 원자재, 크립토 |
| `sentiment` | 시장심리 | 공포, 탐욕 |
| `technical` | 기술적 | 추세추종, 평균회귀 |

#### 5-3. 감성 분석

VADER + 금융 도메인 커스텀 사전을 사용합니다:

```python
from src.processing.sentiment_scorer import score_sentiment, score_items

# 단일 텍스트
result = score_sentiment("Market rallies on strong earnings, bullish outlook ahead")
# → {'compound': 0.85, 'positive': 0.55, 'negative': 0.0, 'neutral': 0.45, 'label': 'very_positive'}

# 여러 항목 일괄 처리
items = [
    {"title": "Stock market surges", "content": "Investors are optimistic"},
    {"title": "Recession fears grow", "content": "Economic data weakens"},
]
scored = score_items(items)
# 각 항목에 sentiment_score, sentiment_label 추가됨
```

**감성 레이블 기준:**
| 레이블 | 점수 범위 |
|--------|-----------|
| `very_negative` | ≤ -0.6 |
| `negative` | -0.6 ~ -0.2 |
| `neutral` | -0.2 ~ +0.05 |
| `positive` | +0.05 ~ +0.2 |
| `very_positive` | > +0.6 |

#### 5-4. 관련성 평가

```python
from src.processing.relevance_scorer import compute_relevance, score_and_filter

# 단일 항목 관련성 평가
rel = compute_relevance("NVIDIA reports record AI chip revenue growth")
# → {
#     'overall_score': 0.75,
#     'affected_assets': ['NVDA'],
#     'primary_theme': 'sector',
#     'theme_scores': {'sector': 0.6, 'asset': 0.2}
# }

# 일괄 평가 + 필터링 (관련성 0.3 미만 제거)
relevant = score_and_filter(scored_items, min_relevance=0.3)
```

#### 5-5. 나비효과 인과 체인 감지

미리 정의된 6개 인과 체인 템플릿에서 트리거를 감지합니다:

```python
from src.processing.butterfly_chain import detect_chains, store_detected_chains

# 트리거 감지만
triggered = detect_chains("Fed raises interest rates by 50bps, hawkish stance")
# → [0]  (인덱스 0 = 금리 인상 체인)

# 감지 + DB 저장
chain_ids = store_detected_chains(db, "Oil supply disrupted in Middle East conflict")
# butterfly_chains + butterfly_chain_links 테이블에 저장
```

**사전 정의 인과 체인 템플릿:**
| # | 트리거 | 최종 영향 |
|---|--------|-----------|
| 0 | Fed 금리 인상 | 신흥국 주식 하락, 글로벌 리스크 악화 |
| 1 | 중동 분쟁 → 원유 공급 차질 | 성장주 매도 |
| 2 | AI 설비투자 가속 | 유틸리티/에너지주 수혜 |
| 3 | 비트코인 신고가 | 규제 강화 → 시장 조정 |
| 4 | 미국 신규 관세 부과 | 테크 섹터 로테이션 |
| 5 | 수익률 곡선 역전 | 안전자산 랠리 (금, 국채, 달러) |

### 6. 데이터 조회 (DB 에이전트)

#### 자연어 질의

```python
from src.database.nl_to_sql import execute_nl_query
from src.database.operations import DatabaseOperations

db = DatabaseOperations()

# 자연어로 질문
result = execute_nl_query(db, "비트코인 RSI가 어떻게 되나요?")
print(f"SQL: {result['sql']}")
print(f"결과: {result['row_count']}행")
for row in result['results']:
    print(row)
```

**지원되는 질문 패턴:**
| 패턴 | 질문 예시 |
|------|-----------|
| 가격 조회 | "AAPL 가격", "price of BTC-USD" |
| RSI 분석 | "과매수 종목", "overbought assets" |
| 감성 분석 | "시장 심리", "sentiment summary" |
| 시그널 | "매수 신호", "buy signals" |
| 추세 | "트렌드 분석", "trend analysis" |
| 나비효과 | "나비효과 체인", "butterfly chains" |
| 종목 목록 | "주식 전체 목록", "crypto prices" |

#### 프리빌트 분석 쿼리

```python
from src.database.queries import AnalyticalQueries

q = AnalyticalQueries(db)

# 최신 가격
q.latest_prices()                    # 전체
q.latest_prices(asset_type="crypto") # 암호화폐만

# 가격 변동률
q.price_change(days=30)              # 30일 변동률

# RSI 과매수/과매도
q.overbought_oversold()

# SMA 기반 추세 분석
q.trend_analysis()

# 감성 분석 요약 (최근 7일)
q.sentiment_summary(days=7)

# 활성 투자 시그널
q.active_signals_summary()

# 나비효과 체인
q.butterfly_chains_active(min_confidence=0.1)

# 단일 자산 360도 뷰
q.asset_360_view("AAPL")

# 포트폴리오 시그널 매트릭스
q.portfolio_signal_matrix()
```

#### 커스텀 읽기 전용 쿼리

```python
# SELECT만 허용 (INSERT/UPDATE/DELETE 차단)
results = db.execute_readonly("""
    SELECT a.ticker, a.name, m.close, m.rsi_14
    FROM market_data m
    JOIN asset_registry a ON m.asset_id = a.id
    WHERE a.asset_type = 'crypto'
    AND m.date = (SELECT MAX(date) FROM market_data WHERE asset_id = m.asset_id)
    ORDER BY m.close DESC
""")
```

### 7. 분석 모듈

#### 트렌드 감지

```python
from src.analysis.trend_detector import (
    get_all_trend_signals,
    classify_trend,
    detect_golden_death_cross,
    detect_macd_crossover,
    detect_bollinger_squeeze,
)

# 전체 자산 트렌드 시그널
signals = get_all_trend_signals(db)
for ticker, sigs in signals.items():
    print(f"{ticker}: {len(sigs)} signals")
    for s in sigs:
        print(f"  {s['type']}: {s.get('signal', s.get('value', ''))}")
```

**감지되는 시그널:**
| 시그널 | 의미 |
|--------|------|
| `golden_cross` | SMA50이 SMA200 상향 돌파 (강세) |
| `death_cross` | SMA50이 SMA200 하향 돌파 (약세) |
| `macd_bullish_cross` | MACD가 시그널선 상향 돌파 |
| `macd_bearish_cross` | MACD가 시그널선 하향 돌파 |
| `bollinger_squeeze` | 볼린저 밴드 폭 축소 (변동성 폭발 임박) |
| `strong_uptrend` | 가격 > SMA20 > SMA50 > SMA200 |
| `strong_downtrend` | 가격 < SMA20 < SMA50 < SMA200 |

#### 리스크 평가

```python
from src.analysis.risk_assessor import assess_market_risk, assess_asset_risk

# 전체 시장 리스크
risk = assess_market_risk(db)
print(f"전체: {risk['overall_risk']} (score: {risk['risk_score']})")
print(f"자산유형별: {risk['risk_by_type']}")
print(f"고위험 자산: {[a['ticker'] for a in risk['high_risk_assets']]}")

# 개별 자산 리스크
asset_id = db.get_asset_id("BTC-USD")
btc_risk = assess_asset_risk(db, asset_id)
print(f"BTC 변동성: {btc_risk['volatility_annualized']}")
print(f"BTC MDD: {btc_risk['max_drawdown']}")
print(f"BTC 리스크: {btc_risk['risk_level']}")
```

**리스크 구성 요소:**
| 요소 | 설명 |
|------|------|
| 연환산 변동성 | 최근 20일 일일수익률의 표준편차 × √252 |
| 최대낙폭(MDD) | 고점 대비 최대 하락률 |
| RSI 극단값 | RSI가 50에서 멀어질수록 리스크 증가 |

#### 교차 테마 분석

```python
from src.analysis.cross_theme import (
    compute_theme_sentiment_matrix,
    detect_theme_divergences,
    cross_asset_correlation_signals,
)

# 테마별 감성 매트릭스
matrix = compute_theme_sentiment_matrix(db, days=30)
for cat, data in matrix.items():
    print(f"{cat}: sentiment={data['avg_sentiment']:.3f}, items={data['total_items']}")

# 테마 간 괴리 감지
divs = detect_theme_divergences(db)
for d in divs:
    print(d['interpretation'])

# 교차 자산 상관 시그널
signals = cross_asset_correlation_signals(db)
```

#### 매크로 지표

```python
from src.collection.macro_data import get_yield_curve_snapshot, is_yield_curve_inverted
from src.collection.crypto_data import get_btc_fear_indicator, get_crypto_dominance

# 수익률 곡선
yc = get_yield_curve_snapshot(db)
print(f"3M: {yc['3m']}%, 10Y: {yc['10y']}%")
print(f"역전 여부: {is_yield_curve_inverted(db)}")

# BTC 공포/탐욕 프록시
btc_fear = get_btc_fear_indicator(db)
print(f"BTC: {btc_fear['indicator']} (score: {btc_fear['score']})")

# 크립토 시가총액 비중
dominance = get_crypto_dominance(db)
```

### 8. 포트폴리오 배분 생성

```python
from src.analysis.allocation_engine import generate_allocation, store_allocation_as_report

# 위험성향별 배분 생성
for profile in ['conservative', 'moderate', 'aggressive']:
    result = generate_allocation(db, risk_tolerance=profile)
    print(f"\n=== {profile.upper()} ===")
    for asset_type, weight in sorted(result['allocation'].items(), key=lambda x: -x[1]):
        print(f"  {asset_type:12s}: {weight:5.1f}%")
    print(f"  합계: {result['total_weight']}%")

# 보고서로 저장
result = generate_allocation(db, risk_tolerance='moderate')
report_id = store_allocation_as_report(db, result)
print(f"보고서 ID: {report_id}")

# 최신 보고서 조회
report = db.get_latest_report("adhoc")
```

**배분 제약 조건:**
| 자산 유형 | 최소 | 최대 |
|-----------|------|------|
| 주식 | 0% | 70% |
| 채권 | 0% | 50% |
| 원자재 | 0% | 25% |
| 암호화폐 | 0% | 15% |
| FX | 0% | 10% |
| 현금 | 5% | 100% |

---

## 에이전트 사용법

Claude Code에서 에이전트를 직접 호출할 수 있습니다:

```
# 투자 자문 요청 (메인 오케스트레이터)
@investment-advisor 현재 시장 상황에서 자산 배분 전략을 추천해줘

# 데이터 수집 요청
@info-collector 최근 30일간 주요 기술주 데이터를 수집해줘

# 데이터 처리 요청
@data-processor 수집된 뉴스 데이터를 처리해줘

# DB 질의
@db-agent 비트코인의 최근 RSI와 추세를 알려줘
```

에이전트 정의 파일 위치: `.claude/agents/`

---

## 테스트

### 전체 테스트 실행

```bash
pytest tests/ -v
```

현재 **65개 테스트** 전체 통과.

### 개별 테스트 모듈

```bash
# 데이터베이스 CRUD 테스트 (21개)
pytest tests/test_database_operations.py -v

# 시장 데이터 수집 테스트 (8개)
pytest tests/test_market_data.py -v

# 테마 분류 테스트 (12개)
pytest tests/test_categorizer.py -v

# 감성 분석 테스트 (9개)
pytest tests/test_sentiment_scorer.py -v

# 자연어→SQL 테스트 (15개)
pytest tests/test_nl_to_sql.py -v
```

### 테스트 상세 내용

#### `test_database_operations.py` (21개)
| 클래스 | 테스트 항목 |
|--------|------------|
| `TestDataSources` | 시드 데이터 확인, upsert, 중복 갱신 |
| `TestAssetRegistry` | 자산 등록, ID 조회, 유형별 필터링 |
| `TestRawDataItems` | 삽입, 해시 중복 체크, 미처리 조회, 처리 완료 마킹 |
| `TestMarketData` | OHLCV upsert, 기술적 지표 업데이트, 날짜 범위 조회 |
| `TestProcessedData` | 삽입 및 관련성 필터 조회 |
| `TestInvestmentSignals` | 시그널 삽입 및 활성 시그널 조회 |
| `TestButterflyChains` | 체인 생성, 링크 추가, 요약 조회 |
| `TestReadonlyQuery` | SELECT 허용, INSERT/DELETE 차단 |
| `TestAdvisoryReports` | 보고서 삽입 및 최신 조회 |

#### `test_market_data.py` (8개)
| 클래스 | 테스트 항목 |
|--------|------------|
| `TestSafeFloat` | float, int, None, NaN, 문자열 변환 |
| `TestFetchOHLCV` | 유효/무효 티커 데이터 가져오기 |
| `TestRegisterAsset` | 수동/자동 자산 유형 등록 |

#### `test_categorizer.py` (12개)
| 클래스 | 테스트 항목 |
|--------|------------|
| `TestMatchKeywords` | 완전 일치, 부분 일치, 빈 값, 대소문자 |
| `TestCategorizeItem` | 매크로/지정학/섹터 분류, 무관 텍스트 |
| `TestGetBestTheme` | 최적 테마 반환, 무관 텍스트 None 반환 |

#### `test_sentiment_scorer.py` (9개)
| 클래스 | 테스트 항목 |
|--------|------------|
| `TestScoreSentiment` | 긍정/부정/중립 판정, 빈 텍스트, 금융 용어, 결과 키 |
| `TestScoreItems` | 일괄 처리, 원본 필드 보존 |

#### `test_nl_to_sql.py` (15개)
| 클래스 | 테스트 항목 |
|--------|------------|
| `TestNlToSql` | 가격/RSI/감성/시그널/추세/나비효과/크립토/기본 질의, SELECT 안전성 |
| `TestExecuteNlQuery` | 반환 구조, 빈 DB 처리, 시드 데이터 실행 |
| `TestSchemaContext` | 스키마 정보 포함 여부 |

### 특정 테스트만 실행

```bash
# 특정 클래스
pytest tests/test_database_operations.py::TestReadonlyQuery -v

# 특정 테스트 함수
pytest tests/test_sentiment_scorer.py::TestScoreSentiment::test_positive_sentiment -v

# 키워드로 필터
pytest tests/ -k "sentiment" -v
```

---

## 데이터베이스 스키마

```
┌─────────────────┐     ┌──────────────────┐
│  data_sources    │     │  asset_registry   │
│  (yfinance 등)   │     │  (AAPL, BTC 등)   │
└────────┬────────┘     └────────┬─────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌──────────────────┐
│ raw_data_items   │     │   market_data     │
│ (원본 뉴스/데이터) │     │  (OHLCV+지표)     │
└────────┬────────┘     └──────────────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────┐
│ processed_data   │────▶│     themes        │
│ (감성/관련성점수)  │     │  (macro 등 18개)   │
└────────┬────────┘     └──────────────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌──────────────────┐
│butterfly│ │investment_signals │
│_chains  │ │ (buy/sell/hold)   │
└────────┘ └────────┬─────────┘
                    │
                    ▼
            ┌──────────────────┐
            │advisory_reports   │
            │ (자문 보고서)      │
            └──────────────────┘
```

---

## 설정 커스터마이징

모든 설정은 `src/utils/config.py`에서 관리합니다:

```python
# 추적 자산 추가/변경
STOCK_TICKERS = ["^GSPC", "AAPL", ...]   # 주식
CRYPTO_TICKERS = ["BTC-USD", ...]         # 암호화폐

# 기술적 지표 파라미터
RSI_PERIOD = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
BOLLINGER_PERIOD, BOLLINGER_STD = 20, 2.0

# 감성 분석 임계값
SENTIMENT_THRESHOLDS = {
    "very_negative": -0.6,
    "negative": -0.2,
    ...
}

# 포트폴리오 배분 제약
ALLOCATION_BOUNDS = {
    "stock": (0.0, 0.70),
    "crypto": (0.0, 0.15),
    "cash": (0.05, 1.0),  # 최소 5% 현금
    ...
}
```

---

## 프로젝트 구조

```
fin_advisor/
├── CLAUDE.md                              # 프로젝트 지침
├── README.md                              # 이 문서
├── requirements.txt                       # 의존성
├── data/
│   └── investment.db                      # SQLite DB (gitignore)
├── src/
│   ├── utils/
│   │   └── config.py                     # 전체 설정값
│   ├── collection/                        # 데이터 수집
│   │   ├── market_data.py                # yfinance OHLCV 래퍼
│   │   ├── technical_indicators.py       # RSI, MACD, BB, SMA
│   │   ├── macro_data.py                # 채권/원자재/FX + 수익률곡선
│   │   ├── crypto_data.py               # 암호화폐 + 공포/탐욕
│   │   └── news_collector.py            # 뉴스 구조화/저장
│   ├── processing/                        # 데이터 처리
│   │   ├── deduplicator.py              # 중복 제거
│   │   ├── categorizer.py               # 테마 분류
│   │   ├── sentiment_scorer.py          # VADER 감성 분석
│   │   ├── relevance_scorer.py          # 관련성 평가
│   │   └── butterfly_chain.py           # 나비효과 인과 체인
│   ├── database/                          # DB 레이어
│   │   ├── schema.py                    # 스키마 정의 + 초기화
│   │   ├── models.py                    # TypedDict 모델
│   │   ├── operations.py                # CRUD 연산
│   │   ├── queries.py                   # 프리빌트 분석 쿼리
│   │   └── nl_to_sql.py                # 자연어→SQL 변환
│   └── analysis/                          # 분석
│       ├── trend_detector.py            # 트렌드/크로스오버/스퀴즈
│       ├── risk_assessor.py             # 변동성/MDD/리스크 평가
│       ├── allocation_engine.py         # 포트폴리오 배분
│       └── cross_theme.py              # 교차 테마 상관분석
├── scripts/
│   ├── init_db.py                        # DB 초기화 CLI
│   ├── collect_market_data.py            # 시장 데이터 수집 CLI
│   └── validate_readonly_query.sh        # SQL 읽기전용 검증 훅
├── tests/
│   ├── test_database_operations.py       # DB CRUD 테스트 (21개)
│   ├── test_market_data.py              # 시장 데이터 테스트 (8개)
│   ├── test_categorizer.py              # 테마 분류 테스트 (12개)
│   ├── test_sentiment_scorer.py         # 감성 분석 테스트 (9개)
│   └── test_nl_to_sql.py               # NL→SQL 테스트 (15개)
└── .claude/agents/
    ├── investment-advisor.md              # 메인 오케스트레이터
    ├── info-collector.md                 # 정보 수집 에이전트
    ├── data-processor.md                 # 데이터 처리 에이전트
    └── db-agent.md                       # DB 질의 에이전트
```
