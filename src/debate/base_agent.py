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
