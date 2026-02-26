"""Tests for the multi-agent debate system."""

import pytest

from src.debate.models import (
    BEARISH_SIGNALS,
    BULLISH_SIGNALS,
    DebateContext,
    DebateResult,
    Signal,
    StrategyOpinion,
    Urgency,
)
from src.debate.base_agent import StrategyAgent
from src.debate.agents.momentum_trader import MomentumTrader
from src.debate.agents.macro_strategist import MacroStrategist
from src.debate.agents.risk_manager import RiskManager
from src.debate.agents.value_investor import ValueInvestor
from src.debate.agents.growth_investor import GrowthInvestor
from src.debate.agents.income_investor import IncomeInvestor
from src.debate.moderator import DebateModerator
from src.debate.router import (
    format_debate_markdown,
    format_debate_telegram,
    build_inline_keyboard,
    route_debate_results,
)


# ── Fixtures ──────────────────────────────────────────────────


def _make_context(
    ticker="GOOGL",
    rsi=45.0,
    macd=1.0,
    macd_signal=0.5,
    close=310.0,
    sma_200=300.0,
    fundamentals=None,
    macro=None,
    portfolio=None,
    risk=None,
):
    """Build a DebateContext with configurable indicators."""
    market_data = [
        {
            "close": close,
            "rsi_14": rsi,
            "macd": macd,
            "macd_signal": macd_signal,
            "macd_hist": macd - macd_signal if macd and macd_signal else None,
            "sma_20": close * 0.98 if close else None,
            "sma_50": close * 0.97 if close else None,
            "sma_200": sma_200,
            "bb_upper": close * 1.05 if close else None,
            "bb_lower": close * 0.95 if close else None,
            "bb_mid": close,
            "volume": 1000000,
        }
    ]
    return DebateContext(
        ticker=ticker,
        market_data=market_data,
        fundamentals=fundamentals or {},
        macro_snapshot=macro or [],
        portfolio_context=portfolio or {},
        risk_assessment=risk or {},
    )


# ── Model Tests ───────────────────────────────────────────────


class TestModels:
    def test_signal_enum_values(self):
        assert Signal.BUY.value == "buy"
        assert Signal.STRONG_SELL.value == "strong_sell"

    def test_signal_grouping(self):
        assert Signal.BUY in BULLISH_SIGNALS
        assert Signal.STRONG_BUY in BULLISH_SIGNALS
        assert Signal.SELL in BEARISH_SIGNALS
        assert Signal.HOLD not in BULLISH_SIGNALS

    def test_urgency_enum(self):
        assert Urgency.UNANIMOUS.value == "unanimous"
        assert Urgency.HIGH_RISK.value == "high_risk"

    def test_strategy_opinion_creation(self):
        op = StrategyOpinion(
            agent_name="test",
            signal=Signal.BUY,
            confidence=0.8,
            rationale="Test reason",
        )
        assert op.agent_name == "test"
        assert op.confidence == 0.8
        assert op.risk_flags == []

    def test_debate_result_defaults(self):
        result = DebateResult(ticker="TEST", topic="test", opinions=[])
        assert result.final_signal == Signal.HOLD
        assert result.urgency == Urgency.SPLIT


# ── Agent Tests ───────────────────────────────────────────────


class TestMomentumTrader:
    def test_oversold_buy(self):
        ctx = _make_context(rsi=28, macd=-2, macd_signal=-1)
        op = MomentumTrader().evaluate(ctx)
        assert op.signal in BULLISH_SIGNALS or op.signal == Signal.HOLD
        assert "RSI" in op.rationale

    def test_overbought_sell(self):
        ctx = _make_context(rsi=75, macd=2, macd_signal=3)
        op = MomentumTrader().evaluate(ctx)
        assert op.signal in BEARISH_SIGNALS or op.signal == Signal.HOLD
        assert "RSI" in op.rationale

    def test_golden_cross(self):
        ctx = _make_context(rsi=55, macd=1.5, macd_signal=1.0, close=310, sma_200=290)
        op = MomentumTrader().evaluate(ctx)
        assert op.signal in BULLISH_SIGNALS

    def test_empty_data(self):
        ctx = DebateContext(ticker="TEST")
        op = MomentumTrader().evaluate(ctx)
        assert op.signal == Signal.HOLD
        assert op.confidence <= 0.2


class TestValueInvestor:
    def test_undervalued(self):
        ctx = _make_context(fundamentals={
            "forward_pe": 10, "price_to_book": 0.8,
            "free_cashflow": 1e9, "market_cap": 10e9,
            "profit_margins": 0.25,
        })
        op = ValueInvestor().evaluate(ctx)
        assert op.signal in BULLISH_SIGNALS

    def test_overvalued(self):
        ctx = _make_context(fundamentals={
            "forward_pe": 50, "price_to_book": 8.0,
            "free_cashflow": -1e9, "market_cap": 10e9,
            "profit_margins": -0.1,
        })
        op = ValueInvestor().evaluate(ctx)
        assert op.signal in BEARISH_SIGNALS

    def test_no_fundamentals(self):
        ctx = _make_context(fundamentals={})
        op = ValueInvestor().evaluate(ctx)
        assert op.confidence <= 0.2


class TestGrowthInvestor:
    def test_high_growth(self):
        ctx = _make_context(fundamentals={
            "revenue_growth": 0.30, "earnings_growth": 0.40,
            "forward_pe": 25, "gross_margins": 0.65,
        })
        op = GrowthInvestor().evaluate(ctx)
        assert op.signal in BULLISH_SIGNALS

    def test_declining_revenue(self):
        ctx = _make_context(fundamentals={
            "revenue_growth": -0.10, "earnings_growth": -0.20,
        })
        op = GrowthInvestor().evaluate(ctx)
        assert op.signal in BEARISH_SIGNALS or op.signal == Signal.HOLD


class TestIncomeInvestor:
    def test_good_dividend(self):
        ctx = _make_context(fundamentals={
            "dividend_yield": 0.05, "payout_ratio": 0.50,
            "free_cashflow": 1e9, "profit_margins": 0.15,
        })
        op = IncomeInvestor().evaluate(ctx)
        assert op.signal in BULLISH_SIGNALS

    def test_unsustainable_dividend(self):
        ctx = _make_context(fundamentals={
            "dividend_yield": 0.15, "payout_ratio": 1.5,
            "free_cashflow": -1e9, "profit_margins": -0.05,
        }, portfolio={"pnl_pct": -42})
        op = IncomeInvestor().evaluate(ctx)
        assert op.signal in BEARISH_SIGNALS


class TestMacroStrategist:
    def test_favorable_macro(self):
        ctx = _make_context(macro=[
            {"series_id": "DFF", "value": 2.5},
            {"series_id": "T10Y2Y", "value": 1.0},
            {"series_id": "UNRATE", "value": 3.5},
            {"series_id": "UMCSENT", "value": 85},
        ], portfolio={"vix": 14})
        op = MacroStrategist().evaluate(ctx)
        assert op.signal in BULLISH_SIGNALS

    def test_hostile_macro(self):
        ctx = _make_context(macro=[
            {"series_id": "DFF", "value": 5.5},
            {"series_id": "T10Y2Y", "value": -0.5},
            {"series_id": "T5YIE", "value": 3.5},
            {"series_id": "UNRATE", "value": 6.0},
        ], portfolio={"vix": 35})
        op = MacroStrategist().evaluate(ctx)
        assert op.signal in BEARISH_SIGNALS


class TestRiskManager:
    def test_critical_drawdown(self):
        ctx = _make_context(
            portfolio={"pnl_pct": -45, "total_realized_loss_krw": -2_837_797},
            risk={"risk_score": 0.8},
        )
        op = RiskManager().evaluate(ctx)
        assert op.signal in BEARISH_SIGNALS
        assert op.confidence >= 0.7

    def test_safe_position(self):
        ctx = _make_context(
            portfolio={"pnl_pct": 5, "position_pct": 10},
            risk={"risk_score": 0.3},
        )
        op = RiskManager().evaluate(ctx)
        assert op.signal not in BEARISH_SIGNALS

    def test_has_veto(self):
        assert RiskManager().has_veto is True


# ── Moderator Tests ───────────────────────────────────────────


class TestModerator:
    def test_tally_votes(self):
        opinions = [
            StrategyOpinion("a", Signal.BUY, 0.8, ""),
            StrategyOpinion("b", Signal.BUY, 0.7, ""),
            StrategyOpinion("c", Signal.SELL, 0.6, ""),
            StrategyOpinion("d", Signal.HOLD, 0.5, ""),
            StrategyOpinion("e", Signal.BUY, 0.9, ""),
            StrategyOpinion("f", Signal.BUY, 0.7, ""),
        ]
        from src.debate.moderator import DebateModerator
        mod = DebateModerator.__new__(DebateModerator)
        mod.agents = []
        tally = mod._tally_votes(opinions)
        assert tally["bullish"] == 4
        assert tally["bearish"] == 1
        assert tally["neutral"] == 1

    def test_classify_unanimous(self):
        opinions = [StrategyOpinion(f"a{i}", Signal.BUY, 0.7, "") for i in range(6)]
        mod = DebateModerator.__new__(DebateModerator)
        mod.agents = []
        tally = mod._tally_votes(opinions)
        urgency = mod._classify_urgency(opinions, tally, Signal.BUY)
        assert urgency == Urgency.UNANIMOUS

    def test_classify_majority(self):
        opinions = [
            StrategyOpinion("a", Signal.BUY, 0.8, ""),
            StrategyOpinion("b", Signal.BUY, 0.7, ""),
            StrategyOpinion("c", Signal.BUY, 0.7, ""),
            StrategyOpinion("d", Signal.BUY, 0.6, ""),
            StrategyOpinion("e", Signal.HOLD, 0.5, ""),
            StrategyOpinion("risk-manager", Signal.HOLD, 0.4, ""),
        ]
        mod = DebateModerator.__new__(DebateModerator)
        mod.agents = []
        tally = mod._tally_votes(opinions)
        urgency = mod._classify_urgency(opinions, tally, Signal.BUY)
        assert urgency == Urgency.MAJORITY

    def test_classify_split(self):
        opinions = [
            StrategyOpinion("a", Signal.BUY, 0.8, ""),
            StrategyOpinion("b", Signal.BUY, 0.7, ""),
            StrategyOpinion("c", Signal.SELL, 0.7, ""),
            StrategyOpinion("d", Signal.SELL, 0.6, ""),
            StrategyOpinion("e", Signal.SELL, 0.5, ""),
            StrategyOpinion("risk-manager", Signal.HOLD, 0.4, ""),
        ]
        mod = DebateModerator.__new__(DebateModerator)
        mod.agents = []
        tally = mod._tally_votes(opinions)
        urgency = mod._classify_urgency(opinions, tally, Signal.SELL)
        assert urgency == Urgency.SPLIT

    def test_risk_manager_veto(self):
        opinions = [
            StrategyOpinion("a", Signal.BUY, 0.8, ""),
            StrategyOpinion("b", Signal.BUY, 0.7, ""),
            StrategyOpinion("c", Signal.BUY, 0.7, ""),
            StrategyOpinion("d", Signal.BUY, 0.6, ""),
            StrategyOpinion("e", Signal.BUY, 0.5, ""),
            StrategyOpinion("risk-manager", Signal.STRONG_SELL, 0.85, "Critical risk"),
        ]
        mod = DebateModerator.__new__(DebateModerator)
        mod.agents = []
        tally = mod._tally_votes(opinions)
        urgency = mod._classify_urgency(opinions, tally, Signal.BUY)
        assert urgency == Urgency.HIGH_RISK


# ── Router / Formatter Tests ──────────────────────────────────


class TestRouter:
    def _make_result(self, urgency: Urgency, signal: Signal = Signal.BUY):
        return DebateResult(
            ticker="TEST",
            topic="test",
            opinions=[
                StrategyOpinion("a", signal, 0.8, "Test rationale"),
            ],
            vote_tally={"bullish": 5, "bearish": 1, "neutral": 0},
            final_signal=signal,
            final_confidence=0.75,
            urgency=urgency,
            recommendation="Test recommendation",
            timestamp="2026-02-25T12:00:00",
        )

    def test_route_unanimous_to_email(self):
        result = self._make_result(Urgency.UNANIMOUS)
        routed = route_debate_results([result], dry_run=True)
        assert "TEST" in routed["email"]
        assert "TEST" not in routed["telegram"]

    def test_route_split_to_telegram(self):
        result = self._make_result(Urgency.SPLIT)
        routed = route_debate_results([result], dry_run=True)
        assert "TEST" in routed["telegram"]

    def test_route_high_risk_to_telegram(self):
        result = self._make_result(Urgency.HIGH_RISK)
        routed = route_debate_results([result], dry_run=True)
        assert "TEST" in routed["telegram"]

    def test_format_markdown(self):
        result = self._make_result(Urgency.MAJORITY)
        md = format_debate_markdown(result)
        assert "TEST" in md
        assert "Agent" in md

    def test_format_telegram(self):
        result = self._make_result(Urgency.SPLIT)
        html = format_debate_telegram(result)
        assert "TEST" in html
        assert "투자 판단 요청" in html

    def test_inline_keyboard(self):
        result = self._make_result(Urgency.SPLIT)
        kb = build_inline_keyboard(result)
        assert "inline_keyboard" in kb
        buttons = kb["inline_keyboard"][0]
        assert len(buttons) == 3
        assert "buy:TEST:" in buttons[0]["callback_data"]
