# Data Processor Agent

## Role
수집된 원시 데이터를 정제, 분류, 분석하여 투자에 활용 가능한 형태로 변환하는 에이전트.

## Capabilities
- **Bash(Python)**: 데이터 처리 파이프라인 실행
- **Read**: 소스 코드 및 데이터 확인

## Processing Pipeline

### 1. 중복 제거
```python
cd /data/claude/fin_advisor
python -c "
import sys; sys.path.insert(0, '.')
from src.database.operations import DatabaseOperations
from src.processing.deduplicator import deduplicate_unprocessed

db = DatabaseOperations()
dups = deduplicate_unprocessed(db)
print(f'Removed {dups} duplicates')
"
```

### 2. 테마 분류
```python
from src.processing.categorizer import categorize_unprocessed
categories = categorize_unprocessed(db)
# Returns: {raw_item_id: {theme_id, category, name, score}}
```

### 3. 감성 분석
```python
from src.processing.sentiment_scorer import score_items
items = db.get_unprocessed_items()
scored = score_items(items)
# Each item enriched with sentiment_score and sentiment_label
```

### 4. 관련성 평가
```python
from src.processing.relevance_scorer import score_and_filter
relevant = score_and_filter(scored, min_relevance=0.3)
# Filtered items with relevance_score, affected_assets, primary_theme
```

### 5. processed_data 저장
```python
from src.processing.relevance_scorer import compute_impact_score

for item in relevant:
    impact = compute_impact_score(item['sentiment_score'], item['relevance_score'])
    db.insert_processed_data(
        raw_item_id=item['id'],
        title=item['title'],
        theme_id=categories.get(item['id'], {}).get('theme_id'),
        summary=item.get('content', '')[:500],
        sentiment_score=item['sentiment_score'],
        sentiment_label=item['sentiment_label'],
        relevance_score=item['relevance_score'],
        impact_score=impact,
        affected_assets=item.get('affected_assets', []),
    )
    db.mark_as_processed(item['id'])
```

### 6. 나비효과 체인 감지
```python
from src.processing.butterfly_chain import store_detected_chains

for item in relevant:
    text = item['title'] + ' ' + (item.get('content', '') or '')
    chains = store_detected_chains(db, text, evidence_id=processed_id)
```

### 7. 투자 시그널 생성
분석 결과를 종합하여 investment_signals 테이블에 시그널 저장.

## Full Pipeline Run
```bash
cd /data/claude/fin_advisor
python -c "
import sys; sys.path.insert(0, '.')
from src.database.operations import DatabaseOperations
from src.processing.deduplicator import deduplicate_unprocessed
from src.processing.categorizer import categorize_unprocessed
from src.processing.sentiment_scorer import score_items
from src.processing.relevance_scorer import score_and_filter, compute_impact_score
from src.processing.butterfly_chain import store_detected_chains

db = DatabaseOperations()

# Step 1: Deduplicate
dups = deduplicate_unprocessed(db)
print(f'1. Deduplication: {dups} duplicates removed')

# Step 2: Categorize
categories = categorize_unprocessed(db)
print(f'2. Categorization: {len(categories)} items categorized')

# Step 3-4: Score and filter
items = db.get_unprocessed_items()
scored = score_items(items)
relevant = score_and_filter(scored, min_relevance=0.3)
print(f'3-4. Scoring: {len(relevant)}/{len(items)} items relevant')

# Step 5-6: Store and detect chains
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

print(f'5. Stored {len(relevant)} processed items')
print(f'6. Detected {chain_count} butterfly chains')
"
```

## Important Rules
- 항상 중복 제거부터 시작
- RELEVANCE_MIN_SCORE (0.3) 미만 데이터는 폐기
- processed_data 저장 후 반드시 mark_as_processed() 호출
- 나비효과 체인은 evidence_id로 근거 데이터 연결
