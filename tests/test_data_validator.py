"""Tests for the data validation / hallucination prevention layer."""

import pytest
from src.debate.data_validator import (
    DataQuality,
    validate_fundamentals,
    assess_data_quality,
    verify_agent_metrics,
    _extract_numeric,
)


class TestValidateFundamentals:
    def test_empty_input(self):
        cleaned, warnings = validate_fundamentals({})
        assert cleaned == {}
        assert "데이터 없음" in warnings[0]

    def test_none_input(self):
        cleaned, warnings = validate_fundamentals(None)
        assert cleaned == {}

    def test_valid_data_passes(self):
        data = {"forward_pe": 15.0, "trailing_pe": 18.0, "price_to_book": 2.5}
        cleaned, warnings = validate_fundamentals(data)
        assert cleaned == data
        assert warnings == []

    def test_out_of_bounds_pe_removed(self):
        data = {"forward_pe": 5000}  # above 2000 max
        cleaned, warnings = validate_fundamentals(data)
        assert cleaned["forward_pe"] is None
        assert len(warnings) == 1
        assert "이상값" in warnings[0]

    def test_negative_market_cap_removed(self):
        data = {"market_cap": -100}
        cleaned, warnings = validate_fundamentals(data)
        assert cleaned["market_cap"] is None

    def test_reasonable_negative_pe_passes(self):
        data = {"trailing_pe": -50.0}  # loss-making company, within bounds
        cleaned, warnings = validate_fundamentals(data)
        assert cleaned["trailing_pe"] == -50.0
        assert warnings == []

    def test_string_values_ignored(self):
        data = {"recommendation_key": "buy", "forward_pe": 15.0}
        cleaned, warnings = validate_fundamentals(data)
        assert cleaned["recommendation_key"] == "buy"
        assert cleaned["forward_pe"] == 15.0

    def test_unknown_keys_passed_through(self):
        data = {"custom_metric": 999999}
        cleaned, warnings = validate_fundamentals(data)
        assert cleaned["custom_metric"] == 999999


class TestAssessDataQuality:
    def test_full_data(self):
        fundamentals = {
            "forward_pe": 15, "trailing_pe": 18, "price_to_book": 2.5,
            "market_cap": 100e9, "free_cashflow": 5e9,
            "profit_margins": 0.20, "gross_margins": 0.55,
            "revenue_growth": 0.15, "earnings_growth": 0.20,
            "dividend_yield": 0.02, "debt_to_equity": 50,
        }
        market_data = [{"date": "2026-03-10", "close": 100, "rsi_14": 50}]
        dq = assess_data_quality(fundamentals, market_data)
        assert dq.completeness == 1.0
        assert dq.is_sufficient
        assert dq.confidence_penalty >= 0.9

    def test_sparse_data(self):
        fundamentals = {"forward_pe": 15}
        market_data = [{"date": "2026-03-10", "close": 100}]
        dq = assess_data_quality(fundamentals, market_data)
        assert dq.completeness < 0.2
        assert not dq.is_sufficient
        assert dq.confidence_penalty == 0.3

    def test_no_market_data(self):
        dq = assess_data_quality({}, [])
        assert any("OHLCV" in w for w in dq.warnings)

    def test_stale_market_data(self):
        fundamentals = {"forward_pe": 15, "trailing_pe": 18, "price_to_book": 2}
        market_data = [{"date": "2026-01-01", "close": 100}]
        dq = assess_data_quality(fundamentals, market_data)
        assert dq.data_age_days > 30
        assert any("일 전" in w for w in dq.warnings)

    def test_missing_indicators_flagged(self):
        market_data = [{"date": "2026-03-10", "close": 100}]  # no rsi/macd
        dq = assess_data_quality({}, market_data)
        assert any("indicator:" in f for f in dq.missing_fields)


class TestVerifyAgentMetrics:
    def test_matching_metrics(self):
        claimed = {"pe_ratio": 15.0, "rsi_14": 45.0}
        fundamentals = {"forward_pe": 15.0}
        indicators = {"rsi_14": 45.0}
        discrepancies = verify_agent_metrics(claimed, fundamentals, indicators)
        assert discrepancies == []

    def test_mismatched_pe(self):
        claimed = {"pe_ratio": 25.0}
        fundamentals = {"forward_pe": 15.0, "trailing_pe": 18.0}
        indicators = {}
        discrepancies = verify_agent_metrics(claimed, fundamentals, indicators)
        assert len(discrepancies) == 1
        assert "불일치" in discrepancies[0]

    def test_no_source_data_no_discrepancy(self):
        """If no source data, can't verify — should NOT flag."""
        claimed = {"pe_ratio": 15.0}
        fundamentals = {}  # no PE data to compare against
        indicators = {}
        discrepancies = verify_agent_metrics(claimed, fundamentals, indicators)
        assert discrepancies == []

    def test_formatted_string_comparison(self):
        claimed = {"dividend_yield": "2.50%"}
        fundamentals = {"dividend_yield": 0.025}
        indicators = {}
        discrepancies = verify_agent_metrics(claimed, fundamentals, indicators)
        assert discrepancies == []


class TestExtractNumeric:
    def test_int(self):
        assert _extract_numeric(42) == 42.0

    def test_float(self):
        assert _extract_numeric(3.14) == 3.14

    def test_percentage_string(self):
        assert _extract_numeric("+12.5%") == 12.5

    def test_dollar_string(self):
        assert _extract_numeric("$1,234.56") == 1234.56

    def test_won_string(self):
        assert _extract_numeric("1,234원") == 1234.0

    def test_none(self):
        assert _extract_numeric(None) is None

    def test_bool(self):
        assert _extract_numeric(True) is None

    def test_unparseable(self):
        assert _extract_numeric("N/A") is None


class TestDataQualityPenalty:
    def test_sufficient_full_data(self):
        dq = DataQuality(
            completeness=1.0,
            available_fields=["a", "b", "c", "d", "e"],
        )
        assert dq.confidence_penalty >= 0.95

    def test_insufficient_data(self):
        dq = DataQuality(
            completeness=0.1,
            available_fields=["a"],
        )
        assert dq.confidence_penalty == 0.3

    def test_stale_data_penalty(self):
        dq = DataQuality(
            completeness=0.8,
            available_fields=["a", "b", "c", "d"],
            data_age_days=10,
        )
        penalty = dq.confidence_penalty
        assert penalty < 0.9  # stale data should reduce

    def test_suspect_fields_penalty(self):
        dq = DataQuality(
            completeness=0.8,
            available_fields=["a", "b", "c", "d"],
            suspect_fields=["x", "y", "z"],
        )
        penalty = dq.confidence_penalty
        assert penalty < 0.85
