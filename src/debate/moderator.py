"""Debate moderator — orchestrates strategy agents and produces final recommendation."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime

from src.database.operations import DatabaseOperations
from src.debate.agents.global_crisis_analyst import GlobalCrisisAnalyst
from src.debate.agents.growth_investor import GrowthInvestor
from src.debate.agents.income_investor import IncomeInvestor
from src.debate.agents.macro_strategist import MacroStrategist
from src.debate.agents.momentum_trader import MomentumTrader
from src.debate.agents.risk_manager import RiskManager
from src.debate.agents.value_investor import ValueInvestor
from src.debate.base_agent import StrategyAgent
from src.debate.context_builder import build_context
from src.debate.models import (
    BEARISH_SIGNALS,
    BULLISH_SIGNALS,
    DebateContext,
    DebateResult,
    Rebuttal,
    Signal,
    StrategyOpinion,
    Urgency,
)

logger = logging.getLogger(__name__)


class DebateModerator:
    """Orchestrates a structured debate among strategy agents."""

    def __init__(self, db: DatabaseOperations):
        self.db = db
        self.agents: list[StrategyAgent] = [
            ValueInvestor(),
            GrowthInvestor(),
            MomentumTrader(),
            IncomeInvestor(),
            MacroStrategist(),
            GlobalCrisisAnalyst(),
            RiskManager(),
        ]

    def run_debate(
        self,
        ticker: str,
        topic: str = "hold_review",
        portfolio_config: dict | None = None,
    ) -> DebateResult:
        """Run a full debate cycle for a single ticker."""
        logger.info("Starting debate for %s (topic: %s)", ticker, topic)

        # Phase 1: Build context
        context = build_context(self.db, ticker, portfolio_config)

        # Phase 2: Collect opinions
        opinions = self._collect_opinions(context)

        # Phase 3: Cross-examination
        rebuttals = self._cross_examine(opinions)

        # Phase 4: Tally votes and determine outcome
        vote_tally = self._tally_votes(opinions)
        final_signal = self._determine_signal(opinions, vote_tally)
        final_confidence = self._compute_confidence(opinions, final_signal)
        urgency = self._classify_urgency(opinions, vote_tally, final_signal)
        dissenting = self._get_dissenting_views(opinions, final_signal)

        # Phase 5: Build recommendation
        recommendation = self._build_recommendation(
            ticker, topic, opinions, final_signal, urgency, dissenting
        )

        return DebateResult(
            ticker=ticker,
            topic=topic,
            opinions=opinions,
            rebuttals=rebuttals,
            vote_tally=vote_tally,
            final_signal=final_signal,
            final_confidence=round(final_confidence, 2),
            urgency=urgency,
            recommendation=recommendation,
            dissenting_views=dissenting,
            timestamp=datetime.now().isoformat(),
        )

    def run_portfolio_debate(
        self,
        tickers: list[str] | None = None,
        portfolio_configs: dict[str, dict] | None = None,
    ) -> list[DebateResult]:
        """Run debates for multiple tickers (e.g., all held positions)."""
        if tickers is None:
            try:
                from scripts.portfolio_config import ALL_TICKERS
                tickers = ALL_TICKERS
            except ImportError:
                tickers = []

        results = []
        for ticker in tickers:
            pf_config = (portfolio_configs or {}).get(ticker, {})
            try:
                result = self.run_debate(ticker, "hold_review", pf_config)
                results.append(result)
            except Exception as e:
                logger.error("Debate failed for %s: %s", ticker, e)
        return results

    # ── Internal methods ──────────────────────────────────────

    def _collect_opinions(self, context: DebateContext) -> list[StrategyOpinion]:
        opinions = []
        for agent in self.agents:
            try:
                opinion = agent.evaluate(context)
                opinions.append(opinion)
                logger.info(
                    "  %s: %s (confidence=%.2f)",
                    agent.name, opinion.signal.value, opinion.confidence,
                )
            except Exception as e:
                logger.error("  %s failed: %s", agent.name, e)
                opinions.append(StrategyOpinion(
                    agent_name=agent.name,
                    signal=Signal.HOLD,
                    confidence=0.1,
                    rationale=f"평가 실패: {e}",
                ))
        return opinions

    def _cross_examine(self, opinions: list[StrategyOpinion]) -> list[Rebuttal]:
        """Let agents with opposing views rebut each other."""
        rebuttals = []
        for i, op_a in enumerate(opinions):
            for j, op_b in enumerate(opinions):
                if i >= j:
                    continue
                # Only rebut if signals are on opposite sides
                a_bull = op_a.signal in BULLISH_SIGNALS
                b_bull = op_b.signal in BULLISH_SIGNALS
                a_bear = op_a.signal in BEARISH_SIGNALS
                b_bear = op_b.signal in BEARISH_SIGNALS
                if (a_bull and b_bear) or (a_bear and b_bull):
                    agent_a = self._get_agent(op_a.agent_name)
                    if agent_a:
                        r = agent_a.rebut(op_a, op_b)
                        if r:
                            rebuttals.append(r)
                    agent_b = self._get_agent(op_b.agent_name)
                    if agent_b:
                        r = agent_b.rebut(op_b, op_a)
                        if r:
                            rebuttals.append(r)
        return rebuttals

    def _get_agent(self, name: str) -> StrategyAgent | None:
        for a in self.agents:
            if a.name == name:
                return a
        return None

    def _tally_votes(self, opinions: list[StrategyOpinion]) -> dict[str, int]:
        """Count votes by signal category (bullish/bearish/neutral)."""
        counter: dict[str, int] = {"bullish": 0, "bearish": 0, "neutral": 0}
        for op in opinions:
            if op.signal in BULLISH_SIGNALS:
                counter["bullish"] += 1
            elif op.signal in BEARISH_SIGNALS:
                counter["bearish"] += 1
            else:
                counter["neutral"] += 1
        return counter

    def _determine_signal(
        self, opinions: list[StrategyOpinion], tally: dict[str, int]
    ) -> Signal:
        """Determine final signal by confidence-weighted voting."""
        weights: dict[Signal, float] = Counter()
        for op in opinions:
            weights[op.signal] += op.confidence

        if not weights:
            return Signal.HOLD

        # Find the signal with highest confidence weight
        best = max(weights, key=lambda s: weights[s])

        # If it's a strong signal, check if there's enough support
        total_weight = sum(weights.values())
        best_weight = weights[best]

        if best_weight / total_weight < 0.25:
            return Signal.HOLD

        return best

    def _compute_confidence(
        self, opinions: list[StrategyOpinion], final_signal: Signal
    ) -> float:
        """Compute final confidence as weighted average of agreeing agents."""
        agreeing = [
            op for op in opinions
            if op.signal == final_signal
            or (op.signal in BULLISH_SIGNALS and final_signal in BULLISH_SIGNALS)
            or (op.signal in BEARISH_SIGNALS and final_signal in BEARISH_SIGNALS)
        ]
        if not agreeing:
            return 0.3
        return sum(op.confidence for op in agreeing) / len(agreeing)

    def _classify_urgency(
        self,
        opinions: list[StrategyOpinion],
        tally: dict[str, int],
        final_signal: Signal,
    ) -> Urgency:
        """Classify how the result should be routed."""
        total = len(opinions)

        # Risk manager veto check
        risk_opinion = next(
            (op for op in opinions if op.agent_name == "risk-manager"), None
        )
        if risk_opinion and risk_opinion.confidence >= 0.8:
            if (
                risk_opinion.signal in BEARISH_SIGNALS
                and final_signal in BULLISH_SIGNALS
            ):
                return Urgency.HIGH_RISK

        # Unanimous: all on same side
        max_side = max(tally.values())
        if max_side == total:
            return Urgency.UNANIMOUS

        # Majority: clear majority (5+ out of 7, or 4+ out of 6)
        if max_side >= total - 2:
            return Urgency.MAJORITY

        # Split
        return Urgency.SPLIT

    def _get_dissenting_views(
        self, opinions: list[StrategyOpinion], final_signal: Signal
    ) -> list[str]:
        """Collect rationale from agents that disagree with final signal."""
        dissenting = []
        for op in opinions:
            if final_signal in BULLISH_SIGNALS and op.signal in BEARISH_SIGNALS:
                dissenting.append(f"[{op.agent_name}] {op.rationale}")
            elif final_signal in BEARISH_SIGNALS and op.signal in BULLISH_SIGNALS:
                dissenting.append(f"[{op.agent_name}] {op.rationale}")
        return dissenting

    def _build_recommendation(
        self,
        ticker: str,
        topic: str,
        opinions: list[StrategyOpinion],
        final_signal: Signal,
        urgency: Urgency,
        dissenting: list[str],
    ) -> str:
        """Build human-readable recommendation summary."""
        signal_kr = {
            Signal.STRONG_BUY: "적극 매수",
            Signal.BUY: "매수",
            Signal.HOLD: "보유",
            Signal.SELL: "매도",
            Signal.STRONG_SELL: "적극 매도",
        }

        lines = [f"[{ticker}] {signal_kr.get(final_signal, final_signal.value)}"]
        lines.append("")

        # Agent summary
        for op in opinions:
            emoji = {"buy": "+", "strong_buy": "++", "hold": "=",
                     "sell": "-", "strong_sell": "--"}.get(op.signal.value, "?")
            lines.append(
                f"  {emoji} {op.agent_name}: {op.signal.value} "
                f"({op.confidence:.0%}) — {op.rationale}"
            )

        if dissenting:
            lines.append("")
            lines.append("반대 의견:")
            for d in dissenting:
                lines.append(f"  {d}")

        return "\n".join(lines)
