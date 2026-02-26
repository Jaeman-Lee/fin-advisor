"""Layer 2 triage: decide the appropriate response for each detected event."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.pipeline.event_store import DetectedEvent

logger = logging.getLogger(__name__)


@dataclass
class TriageDecision:
    """What to do with a detected event."""

    event: DetectedEvent
    action: str           # 'debate', 'alert_only', 'log_only'
    debate_topic: str     # 'hold_review', 'sell_signal', 'buy_opportunity'
    reason: str


# ── Triage Matrix ────────────────────────────────────────────────────────────
# (event_type, severity, is_held) → (action, debate_topic)

_TRIAGE_RULES: list[tuple] = [
    # Price spikes
    ("price_spike", "critical", True,  "debate",     "hold_review"),
    ("price_spike", "critical", False, "alert_only", ""),
    ("price_spike", "warning",  True,  "alert_only", ""),
    ("price_spike", "warning",  False, "log_only",   ""),

    # RSI transitions
    ("rsi_zone",    "warning",  True,  "debate",     "hold_review"),  # entry to extreme zone
    ("rsi_zone",    "warning",  False, "alert_only", ""),
    ("rsi_zone",    "info",     True,  "alert_only", ""),             # recovery from zone
    ("rsi_zone",    "info",     False, "log_only",   ""),

    # MACD crosses
    ("macd_cross",  "warning",  True,  "debate",     "hold_review"),  # death cross
    ("macd_cross",  "warning",  False, "alert_only", ""),
    ("macd_cross",  "info",     True,  "alert_only", ""),             # golden cross
    ("macd_cross",  "info",     False, "log_only",   ""),

    # VIX spikes → always market-wide
    ("vix_spike",   "critical", None,  "debate",     "hold_review"),  # full portfolio debate
    ("vix_spike",   "warning",  None,  "alert_only", ""),

    # Split-buy triggers
    ("split_buy_trigger", "critical", None, "debate", "buy_opportunity"),
]


class EventTriager:
    """Determines the appropriate response to each detected event."""

    def __init__(self, held_tickers: set[str] | None = None,
                 watchlist_tickers: set[str] | None = None):
        self.held_tickers = held_tickers or set()
        self.watchlist_tickers = watchlist_tickers or set()

    def triage(self, events: list[DetectedEvent]) -> list[TriageDecision]:
        """Assign action to each event based on type, severity, and position status."""
        decisions: list[TriageDecision] = []
        for event in events:
            decision = self._decide(event)
            decisions.append(decision)
            logger.info(
                "Triage: [%s] %s → %s (%s)",
                event.severity, event.description, decision.action, decision.reason,
            )
        return decisions

    def _decide(self, event: DetectedEvent) -> TriageDecision:
        is_held = event.ticker in self.held_tickers if event.ticker else None

        for rule_type, rule_sev, rule_held, action, topic in _TRIAGE_RULES:
            if event.event_type != rule_type:
                continue
            if event.severity != rule_sev:
                continue
            # rule_held=None means "don't care" (market-wide events)
            if rule_held is not None and is_held != rule_held:
                continue

            reason = f"rule: {rule_type}/{rule_sev}/held={rule_held}"
            return TriageDecision(
                event=event, action=action,
                debate_topic=topic, reason=reason,
            )

        # Default fallback: log only
        return TriageDecision(
            event=event, action="log_only",
            debate_topic="", reason="no matching rule",
        )
