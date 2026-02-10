"""TypedDict data models for the investment advisory system."""

from typing import TypedDict


class DataSource(TypedDict, total=False):
    id: int
    name: str
    source_type: str
    base_url: str | None
    description: str | None
    created_at: str
    updated_at: str


class AssetRecord(TypedDict, total=False):
    id: int
    ticker: str
    name: str
    asset_type: str
    exchange: str | None
    currency: str
    is_active: int
    created_at: str


class RawDataItem(TypedDict, total=False):
    id: int
    source_id: int
    title: str
    content: str | None
    url: str | None
    published_at: str | None
    collected_at: str
    data_type: str
    raw_json: str | None
    content_hash: str | None
    is_processed: int


class Theme(TypedDict, total=False):
    id: int
    category: str
    name: str
    description: str | None
    keywords: str | None
    created_at: str


class ProcessedData(TypedDict, total=False):
    id: int
    raw_item_id: int
    theme_id: int | None
    title: str
    summary: str | None
    sentiment_score: float | None
    sentiment_label: str | None
    relevance_score: float | None
    impact_score: float | None
    affected_assets: str | None  # JSON array
    processed_at: str


class MarketDataRecord(TypedDict, total=False):
    id: int
    asset_id: int
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    adj_close: float | None
    sma_20: float | None
    sma_50: float | None
    sma_200: float | None
    rsi_14: float | None
    macd: float | None
    macd_signal: float | None
    macd_hist: float | None
    bb_upper: float | None
    bb_middle: float | None
    bb_lower: float | None


class ButterflyChain(TypedDict, total=False):
    id: int
    name: str
    description: str | None
    trigger_event: str
    final_impact: str | None
    confidence: float | None
    created_at: str


class ButterflyChainLink(TypedDict, total=False):
    id: int
    chain_id: int
    seq_order: int
    cause: str
    effect: str
    mechanism: str | None
    strength: float | None
    evidence_id: int | None


class InvestmentSignal(TypedDict, total=False):
    id: int
    asset_id: int | None
    signal_type: str
    strength: float
    source_type: str
    rationale: str | None
    supporting_data: str | None  # JSON
    valid_from: str
    valid_until: str | None
    created_at: str


class AdvisoryReport(TypedDict, total=False):
    id: int
    report_type: str
    title: str
    executive_summary: str | None
    market_overview: str | None
    recommendations: str | None  # JSON
    risk_assessment: str | None
    signal_ids: str | None       # JSON array
    created_at: str
