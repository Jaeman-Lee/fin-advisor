"""Tests for sentiment scoring module."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.processing.sentiment_scorer import score_sentiment, score_items


class TestScoreSentiment:
    def test_positive_sentiment(self):
        result = score_sentiment("Stock market rallies to all-time high, bullish outlook")
        assert result["compound"] > 0
        assert result["label"] in ("positive", "very_positive")

    def test_negative_sentiment(self):
        result = score_sentiment("Market crash fears as recession looms, bearish selloff")
        assert result["compound"] < 0
        assert result["label"] in ("negative", "very_negative")

    def test_neutral_sentiment(self):
        result = score_sentiment("The committee will meet next week to discuss")
        assert -0.3 < result["compound"] < 0.3

    def test_empty_text(self):
        result = score_sentiment("")
        assert result["compound"] == 0.0
        assert result["label"] == "neutral"

    def test_financial_terms_bullish(self):
        result = score_sentiment("Upgrade outlook, bullish rally with strong buyback program")
        assert result["compound"] > 0.3

    def test_financial_terms_bearish(self):
        result = score_sentiment("Downgrade to underperform, bearish crash with default risk")
        assert result["compound"] < -0.3

    def test_result_keys(self):
        result = score_sentiment("test text")
        assert "compound" in result
        assert "positive" in result
        assert "negative" in result
        assert "neutral" in result
        assert "label" in result


class TestScoreItems:
    def test_score_multiple_items(self):
        items = [
            {"title": "Market surges on positive earnings", "content": "Great results"},
            {"title": "Oil prices plunge on demand fears", "content": "Weak outlook"},
        ]
        results = score_items(items)
        assert len(results) == 2
        assert results[0]["sentiment_score"] > results[1]["sentiment_score"]
        assert "sentiment_label" in results[0]

    def test_preserves_original_fields(self):
        items = [{"title": "Test", "content": "Content", "extra_field": "kept"}]
        results = score_items(items)
        assert results[0]["extra_field"] == "kept"
