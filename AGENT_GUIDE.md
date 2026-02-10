# Agent Operation Guide — 투자 자문 시스템

> **이 파일은 에이전트(AI)가 읽고 즉시 시스템을 운용하기 위한 실행 안내서입니다.**
> 모든 코드 블록은 복사하여 그대로 실행할 수 있습니다.
> 작업 디렉토리: `/data/claude/fin_advisor`

---

## 0. 사전 조건 확인

```bash
cd /data/claude/fin_advisor
python -c "
import sys; sys.path.insert(0, '.')
from src.database.schema import DB_PATH
from pathlib import Path

# DB 존재 여부
if DB_PATH.exists():
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    tables = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()
    assets = conn.execute('SELECT COUNT(*) FROM asset_registry').fetchone()[0]
    market = conn.execute('SELECT COUNT(*) FROM market_data').fetchone()[0]
    raw = conn.execute('SELECT COUNT(*) FROM raw_data_items WHERE is_processed=0').fetchone()[0]
    processed = conn.execute('SELECT COUNT(*) FROM processed_data').fetchone()[0]
    signals = conn.execute('SELECT COUNT(*) FROM investment_signals').fetchone()[0]
    conn.close()
    print(f'DB: {DB_PATH} (OK)')
    print(f'테이블: {len(tables)}개')
    print(f'등록 자산: {assets}개')
    print(f'시장 데이터: {market}행')
    print(f'미처리 원시데이터: {raw}건')
    print(f'처리 완료 데이터: {processed}건')
    print(f'투자 시그널: {signals}건')
else:
    print(f'DB 없음 → 1단계(초기화)부터 시작하세요')
"
```

**판단 기준:**
- DB 없음 → **1단계**부터
- 자산 0개 or 시장 데이터 0행 → **2단계**부터
- 미처리 데이터 > 0 → **4단계** 실행
- 모든 데이터 있음 → **5단계**(분석)로 바로 이동

---

## 1. DB 초기화 (최초 1회)

```bash
cd /data/claude/fin_advisor
python scripts/init_db.py
```

10개 테이블 + 시드 데이터(3 data sources, 18 themes) 생성.

---

## 2. 시장 데이터 수집

### 전체 자산 수집 (권장: 90일 + 지표)

```bash
cd /data/claude/fin_advisor
python scripts/collect_market_data.py --days 90 --indicators
```

### 빠른 수집 (주요 5개만, 테스트용)

```bash
cd /data/claude/fin_advisor
python scripts/collect_market_data.py --tickers "^GSPC" AAPL BTC-USD GC=F "^TNX" --days 30 --indicators
```

### 자산 유형별 수집

```bash
python scripts/collect_market_data.py --asset-type stock --days 90 --indicators
python scripts/collect_market_data.py --asset-type crypto --days 90 --indicators
python scripts/collect_market_data.py --asset-type commodity --days 90 --indicators
python scripts/collect_market_data.py --asset-type bond --days 90 --indicators
```

---

## 3. 뉴스 수집

에이전트는 **WebSearch 도구**로 뉴스를 검색한 뒤 아래 코드로 저장합니다.

### 3-1. WebSearch 실행

아래 쿼리를 WebSearch로 검색하세요:

```
Federal Reserve interest rate outlook 2026
US China trade tariff impact 2026
AI semiconductor NVIDIA market outlook 2026
stock market forecast S&P 500 2026
Bitcoin cryptocurrency market analysis 2026
gold commodity price forecast 2026
US treasury bond yield analysis 2026
global recession risk economic outlook 2026
oil price OPEC supply demand 2026
market volatility VIX investor sentiment 2026
```

### 3-2. 검색 결과 저장

WebSearch 결과에서 title, snippet, url을 추출하여 아래 코드에 넣고 실행:

```bash
cd /data/claude/fin_advisor
python3 -c "
import sys; sys.path.insert(0, '.')
from src.collection.news_collector import structure_search_result, store_news_items
from src.database.operations import DatabaseOperations

db = DatabaseOperations()
items = [
    # 아래 형식으로 WebSearch 결과를 추가 (원하는 만큼)
    structure_search_result({
        'title': '여기에 제목',
        'snippet': '여기에 요약/설명',
        'url': 'https://example.com/article'
    }),
    # ... 추가 항목 ...
]
stored = store_news_items(db, items)
print(f'저장 완료: {len(stored)}건 (중복 제외)')
"
```

**중요:** content_hash 기반 자동 중복 방지가 적용되므로 같은 데이터를 여러 번 넣어도 안전합니다.

---

## 4. 데이터 처리 파이프라인

미처리 원시 데이터(raw_data_items)를 정제합니다. **3단계 이후에 실행하세요.**

```bash
cd /data/claude/fin_advisor
python3 -c "
import sys; sys.path.insert(0, '.')
from src.database.operations import DatabaseOperations
from src.processing.deduplicator import deduplicate_unprocessed
from src.processing.categorizer import categorize_unprocessed
from src.processing.sentiment_scorer import score_items
from src.processing.relevance_scorer import score_and_filter, compute_impact_score
from src.processing.butterfly_chain import store_detected_chains

db = DatabaseOperations()

# 1) 중복 제거
dups = deduplicate_unprocessed(db)
print(f'[1/5] 중복 제거: {dups}건')

# 2) 테마 분류
categories = categorize_unprocessed(db)
print(f'[2/5] 테마 분류: {len(categories)}건')

# 3) 감성 분석 + 4) 관련성 평가
items = db.get_unprocessed_items()
scored = score_items(items)
relevant = score_and_filter(scored, min_relevance=0.3)
print(f'[3-4/5] 감성+관련성: {len(relevant)}/{len(items)}건 통과')

# 5) 저장 + 나비효과 체인 감지
chain_count = 0
for item in relevant:
    impact = compute_impact_score(item['sentiment_score'], item['relevance_score'])
    theme_info = categories.get(item['id'], {})
    proc_id = db.insert_processed_data(
        raw_item_id=item['id'],
        title=item['title'],
        theme_id=theme_info.get('theme_id'),
        summary=(item.get('content', '') or '')[:500],
        sentiment_score=item['sentiment_score'],
        sentiment_label=item['sentiment_label'],
        relevance_score=item['relevance_score'],
        impact_score=impact,
        affected_assets=item.get('affected_assets', []),
    )
    db.mark_as_processed(item['id'])
    text = item['title'] + ' ' + (item.get('content', '') or '')
    chains = store_detected_chains(db, text, evidence_id=proc_id)
    chain_count += len(chains)

print(f'[5/5] 저장: {len(relevant)}건, 나비효과 체인: {chain_count}건')
"
```

---

## 5. 분석 및 자문 생성

### 5-1. 시장 현황 조회

```bash
cd /data/claude/fin_advisor
python3 -c "
import sys; sys.path.insert(0, '.')
from src.database.queries import AnalyticalQueries
from src.database.operations import DatabaseOperations

db = DatabaseOperations()
q = AnalyticalQueries(db)

print('=== 최신 가격 ===')
for p in q.latest_prices():
    rsi = f'{p[\"rsi_14\"]:.1f}' if p.get('rsi_14') else 'N/A'
    close = p.get('close') or 0
    print(f'  {p[\"ticker\"]:12s} {p.get(\"asset_type\",\"\"):10s} \${close:>12,.2f}  RSI={rsi}')

print('\n=== 과매수/과매도 ===')
for o in q.overbought_oversold():
    print(f'  {o[\"ticker\"]:12s} RSI={o[\"rsi_14\"]:.1f} → {o[\"rsi_signal\"]}')

print('\n=== 30일 가격 변동률 ===')
for c in q.price_change(days=30):
    pct = c.get('change_pct')
    if pct is not None:
        print(f'  {c[\"ticker\"]:12s} {c.get(\"asset_type\",\"\"):10s} {pct:+.2f}%')
"
```

### 5-2. 추세 분석

```bash
cd /data/claude/fin_advisor
python3 -c "
import sys; sys.path.insert(0, '.')
from src.database.operations import DatabaseOperations
from src.database.queries import AnalyticalQueries

db = DatabaseOperations()
q = AnalyticalQueries(db)

print('=== SMA 추세 ===')
for t in q.trend_analysis():
    print(f'  {t[\"ticker\"]:12s} {t.get(\"asset_type\",\"\"):10s} → {t.get(\"trend\",\"unknown\")}')
"
```

### 5-3. 리스크 평가

```bash
cd /data/claude/fin_advisor
python3 -c "
import sys; sys.path.insert(0, '.')
from src.database.operations import DatabaseOperations
from src.analysis.risk_assessor import assess_market_risk

db = DatabaseOperations()
risk = assess_market_risk(db)

print(f'전체 리스크: {risk[\"overall_risk\"]} (score: {risk.get(\"risk_score\")})')
print(f'평가 자산: {risk.get(\"total_assets_assessed\", 0)}개')
print()
for atype, r in risk.get('risk_by_type', {}).items():
    print(f'  {atype:12s}: {r[\"risk_level\"]:10s} (score={r[\"avg_risk\"]:.3f}, n={r[\"count\"]})')
print()
print('고위험 자산 TOP 5:')
for a in risk.get('high_risk_assets', [])[:5]:
    print(f'  {a[\"ticker\"]:12s} {a.get(\"risk_level\",\"\"):10s} 변동성={a.get(\"volatility_annualized\",\"N/A\")} MDD={a.get(\"max_drawdown\",\"N/A\")}')
"
```

### 5-4. 매크로 지표 (수익률 곡선 + BTC 공포/탐욕)

```bash
cd /data/claude/fin_advisor
python3 -c "
import sys; sys.path.insert(0, '.')
from src.database.operations import DatabaseOperations
from src.collection.macro_data import get_yield_curve_snapshot, is_yield_curve_inverted
from src.collection.crypto_data import get_btc_fear_indicator

db = DatabaseOperations()

yc = get_yield_curve_snapshot(db)
print('=== 수익률 곡선 ===')
for mat, val in yc.items():
    print(f'  {mat}: {val}')
print(f'  역전 여부: {is_yield_curve_inverted(db)}')

btc = get_btc_fear_indicator(db)
print(f'\n=== BTC 공포/탐욕 ===')
print(f'  {btc[\"indicator\"]} (score: {btc[\"score\"]})')
"
```

### 5-5. 나비효과 체인 조회

```bash
cd /data/claude/fin_advisor
python3 -c "
import sys; sys.path.insert(0, '.')
from src.database.queries import AnalyticalQueries
from src.database.operations import DatabaseOperations

db = DatabaseOperations()
q = AnalyticalQueries(db)
chains = q.butterfly_chains_active(min_confidence=0.05)
if chains:
    for c in chains:
        print(f'[신뢰도 {c.get(\"confidence\",0):.1%}] {c[\"trigger_event\"]} → {c[\"final_impact\"]}')
        if c.get('chain_detail'):
            print(f'  경로: {c[\"chain_detail\"]}')
        print()
else:
    print('감지된 나비효과 체인 없음 (뉴스 수집+처리 후 다시 확인)')
"
```

### 5-6. 교차 테마 괴리 감지

```bash
cd /data/claude/fin_advisor
python3 -c "
import sys; sys.path.insert(0, '.')
from src.database.operations import DatabaseOperations
from src.analysis.cross_theme import detect_theme_divergences

db = DatabaseOperations()
divs = detect_theme_divergences(db)
if divs:
    for d in divs:
        print(f'[괴리] {d[\"theme_a\"]} vs {d[\"theme_b\"]} (차이: {d[\"divergence_magnitude\"]:.3f})')
        print(f'  → {d[\"interpretation\"]}')
else:
    print('테마 간 괴리 없음 (뉴스 데이터 처리 후 다시 확인)')
"
```

### 5-7. 포트폴리오 배분 생성

```bash
cd /data/claude/fin_advisor
python3 -c "
import sys; sys.path.insert(0, '.')
from src.database.operations import DatabaseOperations
from src.analysis.allocation_engine import generate_allocation, store_allocation_as_report
import json

db = DatabaseOperations()

for profile in ['conservative', 'moderate', 'aggressive']:
    result = generate_allocation(db, risk_tolerance=profile)
    print(f'\n=== {profile.upper()} ===')
    for atype, weight in sorted(result['allocation'].items(), key=lambda x: -x[1]):
        rationale = result['rationale'].get(atype, '')
        print(f'  {atype:12s}: {weight:5.1f}%  | {rationale[:70]}')
    print(f'  합계: {result[\"total_weight\"]}%')

# 중립형 보고서 저장
mod = generate_allocation(db, risk_tolerance='moderate')
rid = store_allocation_as_report(db, mod)
print(f'\n보고서 저장 완료 (ID={rid})')
"
```

---

## 6. 자연어 질의 (DB 에이전트 역할)

사용자의 자연어 질문을 SQL로 변환하여 답변합니다.

```bash
cd /data/claude/fin_advisor
python3 -c "
import sys; sys.path.insert(0, '.')
from src.database.nl_to_sql import execute_nl_query
from src.database.operations import DatabaseOperations
import json

db = DatabaseOperations()

# ── 질문을 여기에 입력 ──
question = '비트코인 RSI가 어떻게 되나요?'
# ────────────────────────

result = execute_nl_query(db, question)
print(f'질문: {result[\"question\"]}')
print(f'SQL: {result[\"sql\"][:200]}')
print(f'결과: {result[\"row_count\"]}행')
for row in result['results'][:20]:
    print(json.dumps(row, indent=2, default=str, ensure_ascii=False))
"
```

**인식되는 질문 패턴:**
- 가격: `"AAPL 가격"`, `"price of BTC-USD"`
- RSI: `"과매수 종목"`, `"RSI overbought"`
- 감성: `"시장 심리"`, `"sentiment"`
- 시그널: `"매수 신호"`, `"buy signal"`
- 추세: `"트렌드"`, `"trend"`
- 나비효과: `"나비효과 체인"`, `"butterfly chain"`
- 종목: `"주식 목록"`, `"crypto prices"`

패턴에 안 맞으면 DB 요약 통계가 반환됩니다.

### 커스텀 SQL 직접 실행 (SELECT만)

```bash
cd /data/claude/fin_advisor
python3 -c "
import sys; sys.path.insert(0, '.')
from src.database.operations import DatabaseOperations
import json

db = DatabaseOperations()

# ── SQL을 여기에 입력 (SELECT만 가능) ──
sql = '''
    SELECT a.ticker, a.name, a.asset_type, m.date, m.close, m.rsi_14
    FROM market_data m
    JOIN asset_registry a ON m.asset_id = a.id
    WHERE m.date = (SELECT MAX(date) FROM market_data WHERE asset_id = m.asset_id)
    ORDER BY a.asset_type, m.close DESC
'''
# ───────────────────────────────────────

results = db.execute_readonly(sql)
for r in results:
    print(json.dumps(r, indent=2, default=str, ensure_ascii=False))
"
```

---

## 7. 투자 시그널 수동 등록

분석 결과에 기반하여 투자 시그널을 직접 등록할 수 있습니다:

```bash
cd /data/claude/fin_advisor
python3 -c "
import sys; sys.path.insert(0, '.')
from src.database.operations import DatabaseOperations

db = DatabaseOperations()

# 예: AAPL 매수 시그널 등록
asset_id = db.get_asset_id('AAPL')
db.insert_signal(
    signal_type='buy',          # buy, sell, hold, overweight, underweight
    strength=0.75,              # 0.0 ~ 1.0
    source_type='composite',    # technical, fundamental, sentiment, composite
    asset_id=asset_id,
    rationale='RSI 과매도 영역 접근 + MACD 강세 크로스 발생',
    valid_until='2026-03-10',   # 시그널 유효기한 (None = 무기한)
)
print('시그널 등록 완료')

# 활성 시그널 조회
for s in db.get_active_signals():
    print(f'  {s.get(\"ticker\",\"N/A\"):12s} {s[\"signal_type\"]:10s} 강도={s[\"strength\"]}  {s.get(\"rationale\",\"\")}')
"
```

---

## 8. 전체 워크플로우 한 번에 실행

**"데이터 수집부터 배분 추천까지"** 원스텝으로:

```bash
cd /data/claude/fin_advisor

# A) DB 초기화 (최초 1회만)
python scripts/init_db.py

# B) 시장 데이터 수집 + 지표
python scripts/collect_market_data.py --days 90 --indicators

# C) 종합 분석 + 배분
python3 -c "
import sys; sys.path.insert(0, '.')
from src.database.operations import DatabaseOperations
from src.database.queries import AnalyticalQueries
from src.analysis.allocation_engine import generate_allocation, store_allocation_as_report
from src.analysis.risk_assessor import assess_market_risk
from src.collection.macro_data import get_yield_curve_snapshot, is_yield_curve_inverted
from src.collection.crypto_data import get_btc_fear_indicator
import json

db = DatabaseOperations()
q = AnalyticalQueries(db)

# 시장 현황
print('='*60)
print(' 시장 현황')
print('='*60)
for p in q.latest_prices():
    rsi = f'{p[\"rsi_14\"]:.1f}' if p.get('rsi_14') else 'N/A'
    print(f'  {p[\"ticker\"]:12s} {p.get(\"asset_type\",\"\"):8s} \${(p.get(\"close\") or 0):>12,.2f} RSI={rsi}')

# 과매수/과매도
print('\n과매수/과매도:')
obs = q.overbought_oversold()
for o in obs:
    print(f'  {o[\"ticker\"]:12s} RSI={o[\"rsi_14\"]:.1f} → {o[\"rsi_signal\"]}')
if not obs:
    print('  없음')

# 30일 변동
print('\n30일 변동률 TOP/BOTTOM 5:')
changes = q.price_change(days=30)
changes_valid = [c for c in changes if c.get('change_pct') is not None]
for c in changes_valid[:5]:
    print(f'  {c[\"ticker\"]:12s} {c[\"change_pct\"]:+.2f}%')
print('  ...')
for c in changes_valid[-5:]:
    print(f'  {c[\"ticker\"]:12s} {c[\"change_pct\"]:+.2f}%')

# 수익률 곡선
yc = get_yield_curve_snapshot(db)
inv = is_yield_curve_inverted(db)
print(f'\n수익률 곡선: 3m={yc.get(\"3m\")} 10y={yc.get(\"10y\")} 30y={yc.get(\"30y\")} 역전={inv}')

# BTC
btc = get_btc_fear_indicator(db)
print(f'BTC 공포/탐욕: {btc[\"indicator\"]} (score={btc[\"score\"]})')

# 리스크
risk = assess_market_risk(db)
print(f'\n전체 리스크: {risk[\"overall_risk\"]} (score={risk.get(\"risk_score\")})')
for at, rd in risk.get('risk_by_type', {}).items():
    print(f'  {at:12s}: {rd[\"risk_level\"]}')

# 포트폴리오 배분
print('\n' + '='*60)
print(' 포트폴리오 배분 추천')
print('='*60)
for profile in ['conservative', 'moderate', 'aggressive']:
    alloc = generate_allocation(db, risk_tolerance=profile)
    parts = ' | '.join(f'{at}:{w:.0f}%' for at, w in sorted(alloc['allocation'].items(), key=lambda x:-x[1]))
    print(f'  {profile:14s}: {parts}')

# 보고서 저장
mod = generate_allocation(db, risk_tolerance='moderate')
rid = store_allocation_as_report(db, mod)
print(f'\n보고서 저장: ID={rid}')
"
```

---

## 9. 자문 보고서 작성 가이드

위 분석 결과를 종합하여 사용자에게 보고서를 제공할 때 아래 구조를 따르세요:

```markdown
## 시장 상황 개요
[자산군별 가격, 추세, RSI 현황을 표로 정리]

## 주요 시그널
[기술적: 골든/데스크로스, MACD, 볼린저 스퀴즈]
[매크로: 수익률곡선, 달러, 원유]
[과매수/과매도 종목 목록]

## 나비효과 인과 체인
[감지된 체인과 예상 파급 영향]

## 포트폴리오 배분 추천
[보수/중립/공격 3단계 표]
[각 자산군별 근거]

## 리스크 요인
[고위험 자산, 주요 리스크 시나리오]

## 결론
[핵심 1-2문장]

---
*면책 조항: 본 분석은 데이터 기반 정보 제공 목적이며, 개인화된 투자 조언이 아닙니다.
실제 투자 결정 시 자격을 갖춘 전문 투자 자문사와 상담하시기 바랍니다.*
```

---

## 부록: 주요 모듈 임포트 경로

```python
# ── 항상 먼저 실행 ──
import sys; sys.path.insert(0, '.')

# ── DB ──
from src.database.operations import DatabaseOperations
from src.database.queries import AnalyticalQueries
from src.database.nl_to_sql import execute_nl_query
from src.database.schema import init_db, reset_db

# ── 수집 ──
from src.collection.market_data import collect_market_data, register_asset
from src.collection.technical_indicators import update_indicators_in_db
from src.collection.macro_data import collect_all_macro, get_yield_curve_snapshot, is_yield_curve_inverted
from src.collection.crypto_data import collect_crypto_data, get_btc_fear_indicator, get_crypto_dominance
from src.collection.news_collector import structure_search_result, store_news_items, get_search_queries

# ── 처리 ──
from src.processing.deduplicator import deduplicate_unprocessed
from src.processing.categorizer import categorize_unprocessed, get_best_theme, categorize_item
from src.processing.sentiment_scorer import score_sentiment, score_items
from src.processing.relevance_scorer import compute_relevance, score_and_filter, compute_impact_score
from src.processing.butterfly_chain import detect_chains, store_detected_chains

# ── 분석 ──
from src.analysis.trend_detector import get_all_trend_signals, classify_trend
from src.analysis.risk_assessor import assess_market_risk, assess_asset_risk
from src.analysis.allocation_engine import generate_allocation, store_allocation_as_report
from src.analysis.cross_theme import compute_theme_sentiment_matrix, detect_theme_divergences

# ── 설정 ──
from src.utils.config import ALL_TICKERS, STOCK_TICKERS, CRYPTO_TICKERS, BOND_TICKERS, COMMODITY_TICKERS, FX_TICKERS
```

---

## 부록: 티커 목록

| 유형 | 티커 |
|------|------|
| 주식 | `^GSPC` `^IXIC` `^DJI` `^KS11` `^N225` `^FTSE` `AAPL` `MSFT` `GOOGL` `AMZN` `NVDA` `TSLA` `005930.KS` `000660.KS` |
| 채권 | `^TNX` `^TYX` `^FVX` `^IRX` `TLT` `SHY` |
| 원자재 | `GC=F` `SI=F` `CL=F` `BZ=F` `NG=F` `HG=F` |
| 암호화폐 | `BTC-USD` `ETH-USD` `SOL-USD` `XRP-USD` `ADA-USD` |
| FX | `EURUSD=X` `USDJPY=X` `USDKRW=X` `DX-Y.NYB` |

---

## 부록: 테스트 실행

```bash
cd /data/claude/fin_advisor
pytest tests/ -v                                    # 전체 (65개)
pytest tests/test_database_operations.py -v         # DB CRUD (21개)
pytest tests/test_market_data.py -v                 # 시장 데이터 (8개)
pytest tests/test_categorizer.py -v                 # 테마 분류 (12개)
pytest tests/test_sentiment_scorer.py -v            # 감성 분석 (9개)
pytest tests/test_nl_to_sql.py -v                   # NL→SQL (15개)
```
