"""Alert data classes and enums for the monitoring system."""

from dataclasses import dataclass, field
from enum import Enum


class AlertPriority(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertCategory(str, Enum):
    RSI = "rsi"
    PRICE_CHANGE = "price_change"
    MACD = "macd"
    GOLDEN_DEATH_CROSS = "golden_death_cross"
    BOLLINGER_SQUEEZE = "bollinger_squeeze"
    PORTFOLIO_PNL = "portfolio_pnl"
    SPLIT_BUY_TRIGGER = "split_buy_trigger"
    TIME_TRIGGER = "time_trigger"
    RISK = "risk"


@dataclass
class Alert:
    category: AlertCategory
    priority: AlertPriority
    ticker: str | None
    title: str
    message: str
    dedup_key: str
    permanent_dedup: bool = False  # True for split-buy triggers (one-time only)
    data: dict = field(default_factory=dict)

    @property
    def priority_emoji(self) -> str:
        return {
            AlertPriority.CRITICAL: "\U0001f534",  # red circle
            AlertPriority.WARNING: "\U0001f7e0",   # orange circle
            AlertPriority.INFO: "\U0001f535",       # blue circle
        }[self.priority]
