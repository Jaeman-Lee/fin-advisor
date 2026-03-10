"""Abstract base class for strategy-specialist debate agents."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.debate.models import DebateContext, Rebuttal, StrategyOpinion


class StrategyAgent(ABC):
    """Base class for all strategy-specialist agents.

    Each agent evaluates a ticker from its strategic perspective
    and produces a StrategyOpinion with signal, confidence, and rationale.
    """

    name: str = "base"
    description: str = ""

    @abstractmethod
    def evaluate(self, context: DebateContext) -> StrategyOpinion:
        """Produce an investment opinion for the given context."""
        ...

    def rebut(
        self, own_opinion: StrategyOpinion, opposing: StrategyOpinion
    ) -> Rebuttal | None:
        """Optionally rebut a conflicting opinion.

        Default implementation produces a generic rebuttal
        when signals differ. Subclasses can override for specifics.
        """
        if own_opinion.signal == opposing.signal:
            return None

        return Rebuttal(
            agent_name=self.name,
            target_agent=opposing.agent_name,
            argument=(
                f"{self.name} disagrees with {opposing.agent_name}: "
                f"'{opposing.rationale}' — however, {own_opinion.rationale}"
            ),
        )

    def _latest_indicators(self, context: DebateContext) -> dict:
        """Extract latest technical indicators from market_data."""
        if not context.market_data:
            return {}
        latest = context.market_data[-1]
        return {
            "close": latest.get("close"),
            "rsi_14": latest.get("rsi_14"),
            "macd": latest.get("macd"),
            "macd_signal": latest.get("macd_signal"),
            "macd_hist": latest.get("macd_hist"),
            "sma_20": latest.get("sma_20"),
            "sma_50": latest.get("sma_50"),
            "sma_200": latest.get("sma_200"),
            "bb_upper": latest.get("bb_upper"),
            "bb_lower": latest.get("bb_lower"),
            "bb_mid": latest.get("bb_mid"),
            "volume": latest.get("volume"),
        }

    # Override in subclasses to indicate whether this agent relies on fundamentals
    _needs_fundamentals: bool = True

    def _apply_data_quality_penalty(
        self, confidence: float, context: DebateContext
    ) -> float:
        """Reduce confidence based on data quality.

        Agents MUST call this before returning their opinion to ensure
        confidence reflects actual data availability.
        """
        dq = context.data_quality
        if not self._needs_fundamentals:
            # Agents that don't use fundamentals only get stale-data penalty
            penalty = 1.0
            if dq.data_age_days is not None and dq.data_age_days > 3:
                penalty -= min(dq.data_age_days * 0.02, 0.15)
            return round(max(0.5, confidence * penalty), 2)

        penalty = dq.confidence_penalty
        adjusted = confidence * penalty
        return round(max(0.05, adjusted), 2)

    def _add_data_warnings(
        self, flags: list[str], context: DebateContext
    ) -> None:
        """Add data quality warnings to agent risk flags."""
        if not context.data_quality.is_sufficient:
            flags.append("데이터 부족 — 신뢰도 낮음")
        for w in context.data_quality.warnings[:2]:
            flags.append(f"⚠ {w}")
