"""SQLite schema definition and migration for the investment advisory system."""

import sqlite3
from pathlib import Path

from src.utils.config import DB_PATH, DATA_DIR

SCHEMA_SQL = """
-- ═══════════════════════════════════════════════════════════════════════════
-- 1. data_sources: 데이터 소스 추적
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS data_sources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,       -- 'yfinance', 'websearch', 'manual'
    source_type TEXT NOT NULL,              -- 'market', 'news', 'macro', 'crypto'
    base_url    TEXT,
    description TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ═══════════════════════════════════════════════════════════════════════════
-- 2. asset_registry: 추적 대상 자산 마스터
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS asset_registry (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    asset_type  TEXT NOT NULL,              -- 'stock','bond','commodity','crypto','fx'
    exchange    TEXT,
    currency    TEXT DEFAULT 'USD',
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_asset_type ON asset_registry(asset_type);

-- ═══════════════════════════════════════════════════════════════════════════
-- 3. raw_data_items: 수집된 원본 데이터
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS raw_data_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       INTEGER NOT NULL REFERENCES data_sources(id),
    title           TEXT NOT NULL,
    content         TEXT,
    url             TEXT,
    published_at    TEXT,
    collected_at    TEXT NOT NULL DEFAULT (datetime('now')),
    data_type       TEXT NOT NULL,          -- 'news','price','indicator','report'
    raw_json        TEXT,                   -- original JSON if applicable
    content_hash    TEXT,                   -- SHA-256 for dedup
    is_processed    INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_raw_collected ON raw_data_items(collected_at);
CREATE INDEX IF NOT EXISTS idx_raw_hash ON raw_data_items(content_hash);
CREATE INDEX IF NOT EXISTS idx_raw_processed ON raw_data_items(is_processed);

-- ═══════════════════════════════════════════════════════════════════════════
-- 4. themes: 테마 분류 마스터
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS themes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT NOT NULL,              -- 'macro','geopolitics','sector','asset','sentiment','technical'
    name        TEXT NOT NULL,
    description TEXT,
    keywords    TEXT,                       -- comma-separated keywords
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(category, name)
);

-- ═══════════════════════════════════════════════════════════════════════════
-- 5. processed_data: 정제된 데이터
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS processed_data (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_item_id       INTEGER NOT NULL REFERENCES raw_data_items(id),
    theme_id          INTEGER REFERENCES themes(id),
    title             TEXT NOT NULL,
    summary           TEXT,
    sentiment_score   REAL,                 -- -1.0 to 1.0
    sentiment_label   TEXT,                 -- 'very_negative' .. 'very_positive'
    relevance_score   REAL,                 -- 0.0 to 1.0
    impact_score      REAL,                 -- -1.0 to 1.0 (negative=bearish, positive=bullish)
    affected_assets   TEXT,                 -- JSON array of ticker symbols
    processed_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_proc_theme ON processed_data(theme_id);
CREATE INDEX IF NOT EXISTS idx_proc_sentiment ON processed_data(sentiment_score);

-- ═══════════════════════════════════════════════════════════════════════════
-- 6. market_data: OHLCV + 기술적 지표 시계열
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS market_data (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id    INTEGER NOT NULL REFERENCES asset_registry(id),
    date        TEXT NOT NULL,
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    volume      REAL,
    adj_close   REAL,
    -- Technical indicators (nullable, computed post-collection)
    sma_20      REAL,
    sma_50      REAL,
    sma_200     REAL,
    rsi_14      REAL,
    macd        REAL,
    macd_signal REAL,
    macd_hist   REAL,
    bb_upper    REAL,
    bb_middle   REAL,
    bb_lower    REAL,
    UNIQUE(asset_id, date)
);

CREATE INDEX IF NOT EXISTS idx_market_asset_date ON market_data(asset_id, date);

-- ═══════════════════════════════════════════════════════════════════════════
-- 7. butterfly_chains: 나비효과 인과 체인
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS butterfly_chains (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    description     TEXT,
    trigger_event   TEXT NOT NULL,          -- 체인 시작 이벤트
    final_impact    TEXT,                   -- 최종 예상 영향
    confidence      REAL,                   -- 0.0 to 1.0
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ═══════════════════════════════════════════════════════════════════════════
-- 8. butterfly_chain_links: 체인 구성 링크
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS butterfly_chain_links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chain_id    INTEGER NOT NULL REFERENCES butterfly_chains(id),
    seq_order   INTEGER NOT NULL,           -- 순서 (1, 2, 3, ...)
    cause       TEXT NOT NULL,
    effect      TEXT NOT NULL,
    mechanism   TEXT,                       -- 인과 메커니즘 설명
    strength    REAL,                       -- 0.0 to 1.0
    evidence_id INTEGER REFERENCES processed_data(id),
    UNIQUE(chain_id, seq_order)
);

CREATE INDEX IF NOT EXISTS idx_chain_links ON butterfly_chain_links(chain_id, seq_order);

-- ═══════════════════════════════════════════════════════════════════════════
-- 9. investment_signals: 도출된 투자 시그널
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS investment_signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id        INTEGER REFERENCES asset_registry(id),
    signal_type     TEXT NOT NULL,          -- 'buy','sell','hold','overweight','underweight'
    strength        REAL NOT NULL,          -- 0.0 to 1.0
    source_type     TEXT NOT NULL,          -- 'technical','fundamental','sentiment','composite'
    rationale       TEXT,
    supporting_data TEXT,                   -- JSON: references to processed_data / market_data
    valid_from      TEXT NOT NULL DEFAULT (datetime('now')),
    valid_until     TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_signal_asset ON investment_signals(asset_id);
CREATE INDEX IF NOT EXISTS idx_signal_type ON investment_signals(signal_type);

-- ═══════════════════════════════════════════════════════════════════════════
-- 10. advisory_reports: 생성된 자문 보고서 이력
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS advisory_reports (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type     TEXT NOT NULL,          -- 'daily','weekly','adhoc'
    title           TEXT NOT NULL,
    executive_summary TEXT,
    market_overview TEXT,
    recommendations TEXT,                   -- JSON: asset allocation + rationale
    risk_assessment TEXT,
    signal_ids      TEXT,                   -- JSON array of signal ids used
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ═══════════════════════════════════════════════════════════════════════════
-- 11. portfolio_trades: 실매매 거래 기록
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS portfolio_trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id        INTEGER NOT NULL REFERENCES asset_registry(id),
    trade_date      TEXT NOT NULL,              -- 거래일 (YYYY-MM-DD)
    action          TEXT NOT NULL,              -- 'buy','sell'
    quantity        INTEGER NOT NULL,           -- 주수
    price           REAL NOT NULL,              -- 주당 매수/매도가
    total_cost      REAL NOT NULL,              -- quantity * price
    fees            REAL DEFAULT 0,             -- 수수료
    tranche         INTEGER,                    -- 분할 매수 회차 (1,2,3)
    strategy        TEXT,                       -- 전략명 (예: 'US빅테크과매도')
    report_id       INTEGER REFERENCES advisory_reports(id),
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_trades_asset ON portfolio_trades(asset_id);
CREATE INDEX IF NOT EXISTS idx_trades_date ON portfolio_trades(trade_date);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON portfolio_trades(strategy);

-- ═══════════════════════════════════════════════════════════════════════════
-- 12. alert_log: 알림 전송 이력 (중복 방지용)
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS alert_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    dedup_key   TEXT NOT NULL,                -- 예: 'rsi:GOOGL:oversold:2026-02-22'
    category    TEXT NOT NULL,                -- 'rsi','price_change','macd','golden_cross', etc.
    ticker      TEXT,
    priority    TEXT NOT NULL DEFAULT 'INFO', -- 'INFO','WARNING','CRITICAL'
    message     TEXT NOT NULL,
    sent_at     TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at  TEXT                          -- NULL = 영구 (분할매수 트리거 등)
);

CREATE INDEX IF NOT EXISTS idx_alert_dedup ON alert_log(dedup_key);
CREATE INDEX IF NOT EXISTS idx_alert_sent ON alert_log(sent_at);

-- ═══════════════════════════════════════════════════════════════════════════
-- 13. macro_indicators: FRED 매크로 경제 지표 시계열
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS macro_indicators (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id   TEXT NOT NULL,              -- FRED series ID (e.g. 'DFF', 'UNRATE')
    date        TEXT NOT NULL,              -- YYYY-MM-DD
    value       REAL,                       -- 지표 값 (NULL = 결측)
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(series_id, date)
);

CREATE INDEX IF NOT EXISTS idx_macro_series_date ON macro_indicators(series_id, date);

-- ═══════════════════════════════════════════════════════════════════════════
-- Seed: default data sources
-- ═══════════════════════════════════════════════════════════════════════════
INSERT OR IGNORE INTO data_sources (name, source_type, description) VALUES
    ('yfinance', 'market', 'Yahoo Finance market data via yfinance Python library'),
    ('websearch', 'news', 'Web search results for financial news and analysis'),
    ('manual', 'manual', 'Manually entered data or analysis'),
    ('fred', 'macro', 'Federal Reserve Economic Data (FRED) API');

-- Seed: default themes
INSERT OR IGNORE INTO themes (category, name, description, keywords) VALUES
    ('macro', 'Interest Rates', 'Central bank policy and interest rate changes', 'fed,rate,fomc,ecb,boj,monetary policy'),
    ('macro', 'Inflation', 'Consumer and producer price trends', 'cpi,ppi,inflation,deflation,prices'),
    ('macro', 'GDP Growth', 'Economic growth indicators', 'gdp,growth,recession,expansion,employment'),
    ('macro', 'Trade Balance', 'International trade and tariffs', 'trade,tariff,export,import,deficit,surplus'),
    ('geopolitics', 'US-China Relations', 'US-China trade and tech competition', 'china,us-china,tariff,trade war,decoupling'),
    ('geopolitics', 'Middle East', 'Middle East conflicts and oil supply', 'middle east,iran,israel,saudi,opec,oil supply'),
    ('geopolitics', 'Russia-Ukraine', 'Russia-Ukraine conflict and sanctions', 'russia,ukraine,sanctions,energy,europe'),
    ('sector', 'AI & Semiconductors', 'AI boom and semiconductor demand', 'ai,gpu,nvidia,semiconductor,chip,llm'),
    ('sector', 'Energy Transition', 'Clean energy and fossil fuel dynamics', 'renewable,solar,wind,ev,battery,oil transition'),
    ('sector', 'Biotech & Healthcare', 'Biotech innovation and healthcare', 'biotech,pharma,drug,fda,healthcare'),
    ('asset', 'Equities', 'Stock market trends', 'stock,equity,s&p,nasdaq,earnings,valuation'),
    ('asset', 'Fixed Income', 'Bond market and yields', 'bond,treasury,yield,credit,duration'),
    ('asset', 'Commodities', 'Commodity markets', 'gold,oil,copper,commodity,metals'),
    ('asset', 'Crypto', 'Cryptocurrency markets', 'bitcoin,ethereum,crypto,defi,blockchain'),
    ('sentiment', 'Market Fear', 'Fear and volatility indicators', 'vix,fear,panic,crash,correction'),
    ('sentiment', 'Market Greed', 'Greed and risk-on indicators', 'rally,bull,all-time high,euphoria,fomo'),
    ('technical', 'Trend Following', 'Trend-based technical signals', 'sma,ema,trend,breakout,momentum'),
    ('technical', 'Mean Reversion', 'Overbought/oversold signals', 'rsi,bollinger,oversold,overbought,reversion');
"""


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Get a database connection with WAL mode and foreign keys enabled."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | None = None) -> Path:
    """Initialize the database schema. Returns the DB path."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()
    return path


def reset_db(db_path: Path | None = None) -> Path:
    """Drop and recreate the database. USE WITH CAUTION."""
    path = db_path or DB_PATH
    if path.exists():
        path.unlink()
    return init_db(path)
