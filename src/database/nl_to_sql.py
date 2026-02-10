"""Natural language to SQL query conversion for the investment advisory DB.

Uses pattern matching and keyword extraction to convert user questions
into safe, read-only SQL queries.
"""

import re
import logging

from src.database.operations import DatabaseOperations

logger = logging.getLogger(__name__)

# Schema context for query generation
SCHEMA_CONTEXT = """
Tables:
- asset_registry(id, ticker, name, asset_type, exchange, currency, is_active)
- market_data(id, asset_id, date, open, high, low, close, volume, adj_close,
              sma_20, sma_50, sma_200, rsi_14, macd, macd_signal, macd_hist,
              bb_upper, bb_middle, bb_lower)
- processed_data(id, raw_item_id, theme_id, title, summary, sentiment_score,
                 sentiment_label, relevance_score, impact_score, affected_assets, processed_at)
- themes(id, category, name, description, keywords)
- investment_signals(id, asset_id, signal_type, strength, source_type, rationale,
                     supporting_data, valid_from, valid_until)
- butterfly_chains(id, name, description, trigger_event, final_impact, confidence)
- butterfly_chain_links(id, chain_id, seq_order, cause, effect, mechanism, strength)
- advisory_reports(id, report_type, title, executive_summary, market_overview,
                   recommendations, risk_assessment, signal_ids, created_at)
- data_sources(id, name, source_type, base_url, description)

Key relationships:
- market_data.asset_id → asset_registry.id
- processed_data.theme_id → themes.id
- investment_signals.asset_id → asset_registry.id
- butterfly_chain_links.chain_id → butterfly_chains.id
"""

# Pattern-based query templates
QUERY_PATTERNS: list[tuple[re.Pattern, str, tuple]] = [
    # Price queries
    (
        re.compile(r"(?:price|가격|종가).*?(\w[\w.\-=]+)", re.IGNORECASE),
        """SELECT a.ticker, a.name, m.date, m.close, m.volume
           FROM market_data m JOIN asset_registry a ON m.asset_id = a.id
           WHERE a.ticker LIKE ? OR LOWER(a.name) LIKE ?
           ORDER BY m.date DESC LIMIT 10""",
        lambda m: (f"%{m.group(1)}%", f"%{m.group(1).lower()}%"),
    ),
    # RSI queries
    (
        re.compile(r"(?:rsi|과매수|과매도|overbought|oversold)", re.IGNORECASE),
        """SELECT a.ticker, a.name, a.asset_type, m.date, m.close, m.rsi_14,
                  CASE WHEN m.rsi_14 >= 70 THEN 'overbought'
                       WHEN m.rsi_14 <= 30 THEN 'oversold'
                       ELSE 'neutral' END AS signal
           FROM market_data m JOIN asset_registry a ON m.asset_id = a.id
           WHERE m.date = (SELECT MAX(date) FROM market_data WHERE asset_id = m.asset_id)
             AND m.rsi_14 IS NOT NULL
           ORDER BY m.rsi_14 DESC""",
        lambda m: (),
    ),
    # Sentiment queries
    (
        re.compile(r"(?:sentiment|감성|심리|분위기)", re.IGNORECASE),
        """SELECT t.category, t.name, COUNT(*) as count,
                  ROUND(AVG(p.sentiment_score), 3) AS avg_sentiment,
                  ROUND(AVG(p.impact_score), 3) AS avg_impact
           FROM processed_data p
           LEFT JOIN themes t ON p.theme_id = t.id
           WHERE p.processed_at >= datetime('now', '-7 days')
           GROUP BY t.category, t.name
           ORDER BY avg_sentiment DESC""",
        lambda m: (),
    ),
    # Signal queries
    (
        re.compile(r"(?:signal|시그널|신호|buy|sell|매수|매도)", re.IGNORECASE),
        """SELECT s.signal_type, s.strength, s.source_type, s.rationale,
                  a.ticker, a.name, a.asset_type
           FROM investment_signals s
           LEFT JOIN asset_registry a ON s.asset_id = a.id
           WHERE s.valid_until IS NULL OR s.valid_until >= datetime('now')
           ORDER BY s.strength DESC LIMIT 20""",
        lambda m: (),
    ),
    # Trend queries
    (
        re.compile(r"(?:trend|추세|트렌드|uptrend|downtrend)", re.IGNORECASE),
        """SELECT a.ticker, a.name, a.asset_type, m.date, m.close,
                  m.sma_20, m.sma_50, m.sma_200,
                  CASE
                    WHEN m.close > m.sma_20 AND m.sma_20 > m.sma_50 THEN 'strong_up'
                    WHEN m.close > m.sma_50 THEN 'up'
                    WHEN m.close < m.sma_20 AND m.sma_20 < m.sma_50 THEN 'strong_down'
                    WHEN m.close < m.sma_50 THEN 'down'
                    ELSE 'sideways'
                  END AS trend
           FROM market_data m JOIN asset_registry a ON m.asset_id = a.id
           WHERE m.date = (SELECT MAX(date) FROM market_data WHERE asset_id = m.asset_id)
             AND m.sma_50 IS NOT NULL
           ORDER BY a.asset_type, a.ticker""",
        lambda m: (),
    ),
    # Butterfly chain queries
    (
        re.compile(r"(?:butterfly|나비|chain|체인|causal|인과)", re.IGNORECASE),
        """SELECT bc.name, bc.trigger_event, bc.final_impact, bc.confidence,
                  GROUP_CONCAT(bcl.seq_order || '. ' || bcl.cause || ' → ' || bcl.effect, ' | ') as steps
           FROM butterfly_chains bc
           LEFT JOIN butterfly_chain_links bcl ON bc.id = bcl.chain_id
           GROUP BY bc.id
           ORDER BY bc.confidence DESC""",
        lambda m: (),
    ),
    # Asset type queries
    (
        re.compile(r"(?:stock|주식|equity).*(?:list|목록|all|전체)", re.IGNORECASE),
        """SELECT ticker, name, asset_type, currency FROM asset_registry
           WHERE asset_type = 'stock' AND is_active = 1 ORDER BY ticker""",
        lambda m: (),
    ),
    (
        re.compile(r"(?:crypto|암호화폐|코인).*(?:list|목록|all|전체|price|가격)", re.IGNORECASE),
        """SELECT a.ticker, a.name, m.date, m.close, m.rsi_14
           FROM asset_registry a
           LEFT JOIN market_data m ON a.id = m.asset_id
             AND m.date = (SELECT MAX(date) FROM market_data WHERE asset_id = a.id)
           WHERE a.asset_type = 'crypto' AND a.is_active = 1
           ORDER BY a.ticker""",
        lambda m: (),
    ),
]


def nl_to_sql(question: str) -> tuple[str, tuple]:
    """Convert a natural language question to a SQL query.

    Args:
        question: Natural language question.

    Returns:
        Tuple of (sql_query, params). Returns a default query if no pattern matches.
    """
    for pattern, sql_template, param_fn in QUERY_PATTERNS:
        match = pattern.search(question)
        if match:
            params = param_fn(match)
            logger.info(f"NL→SQL: Matched pattern for '{question[:50]}...'")
            return sql_template, params

    # Default: show a summary of what's available
    logger.info(f"NL→SQL: No pattern matched for '{question[:50]}...', returning overview")
    return (
        """SELECT 'assets' AS category, COUNT(*) AS count FROM asset_registry WHERE is_active = 1
           UNION ALL
           SELECT 'market_data_rows', COUNT(*) FROM market_data
           UNION ALL
           SELECT 'processed_items', COUNT(*) FROM processed_data
           UNION ALL
           SELECT 'active_signals', COUNT(*) FROM investment_signals
             WHERE valid_until IS NULL OR valid_until >= datetime('now')
           UNION ALL
           SELECT 'butterfly_chains', COUNT(*) FROM butterfly_chains""",
        (),
    )


def execute_nl_query(db: DatabaseOperations, question: str) -> dict:
    """Execute a natural language query and return results.

    Returns:
        {
            'question': str,
            'sql': str,
            'results': list[dict],
            'row_count': int,
        }
    """
    sql, params = nl_to_sql(question)

    # Safety check
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT"):
        return {
            "question": question,
            "sql": sql,
            "results": [],
            "row_count": 0,
            "error": "Only SELECT queries are allowed",
        }

    try:
        results = db.execute_readonly(sql, params)
        return {
            "question": question,
            "sql": sql,
            "results": results,
            "row_count": len(results),
        }
    except Exception as e:
        logger.error(f"Query execution failed: {e}")
        return {
            "question": question,
            "sql": sql,
            "results": [],
            "row_count": 0,
            "error": str(e),
        }


def get_schema_context() -> str:
    """Return schema context for LLM-based query generation."""
    return SCHEMA_CONTEXT
