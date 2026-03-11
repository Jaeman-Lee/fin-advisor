"""Data models for the multi-agent debate system."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Signal(str, Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


class Urgency(str, Enum):
    UNANIMOUS = "unanimous"       # All agree -> auto-record
    MAJORITY = "majority"         # 4+ agree -> email proposal
    SPLIT = "split"               # 3-3 or close split -> Telegram
    HIGH_RISK = "high_risk"       # Risk manager veto -> Telegram


# Signal grouping for vote tallying
BULLISH_SIGNALS = {Signal.STRONG_BUY, Signal.BUY}
BEARISH_SIGNALS = {Signal.SELL, Signal.STRONG_SELL}
NEUTRAL_SIGNALS = {Signal.HOLD}


@dataclass
class DataQuality:
    """Tracks data completeness and reliability for a context."""

    completeness: float = 0.0
    available_fields: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suspect_fields: list[str] = field(default_factory=list)
    data_age_days: int | None = None

    @property
    def is_sufficient(self) -> bool:
        return len(self.available_fields) >= 3

    @property
    def confidence_penalty(self) -> float:
        if not self.is_sufficient:
            return 0.3
        penalty = 1.0
        penalty -= (1.0 - self.completeness) * 0.3
        penalty -= min(len(self.suspect_fields) * 0.05, 0.2)
        if self.data_age_days is not None and self.data_age_days > 3:
            penalty -= min(self.data_age_days * 0.02, 0.15)
        return max(0.3, penalty)


@dataclass
class DebateContext:
    """Bundled data provided to all strategy agents."""

    ticker: str
    asset_info: dict = field(default_factory=dict)
    market_data: list[dict] = field(default_factory=list)
    trend_signals: list[dict] = field(default_factory=list)
    risk_assessment: dict = field(default_factory=dict)
    sentiment_data: list[dict] = field(default_factory=list)
    macro_snapshot: list[dict] = field(default_factory=list)
    portfolio_context: dict = field(default_factory=dict)
    active_signals: list[dict] = field(default_factory=list)
    fundamentals: dict = field(default_factory=dict)
    global_market_data: dict = field(default_factory=dict)  # VIX, Gold, Oil, DXY, USDKRW latest
    data_quality: DataQuality = field(default_factory=DataQuality)


@dataclass
class StrategyOpinion:
    """A single strategy agent's evaluation."""

    agent_name: str
    signal: Signal
    confidence: float            # 0.0 - 1.0
    rationale: str               # 2-3 sentence explanation
    key_metrics: dict = field(default_factory=dict)
    risk_flags: list[str] = field(default_factory=list)


@dataclass
class Rebuttal:
    """An agent's response to a conflicting opinion."""

    agent_name: str
    target_agent: str
    argument: str


@dataclass
class DebateResult:
    """Final output of a debate session."""

    ticker: str
    topic: str
    opinions: list[StrategyOpinion]
    rebuttals: list[Rebuttal] = field(default_factory=list)
    vote_tally: dict[str, int] = field(default_factory=dict)
    final_signal: Signal = Signal.HOLD
    final_confidence: float = 0.0
    urgency: Urgency = Urgency.SPLIT
    recommendation: str = ""
    dissenting_views: list[str] = field(default_factory=list)
    timestamp: str = ""
