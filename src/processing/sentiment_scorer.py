"""Sentiment analysis using NLTK VADER for financial text."""

import logging

import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer

from src.utils.config import SENTIMENT_THRESHOLDS

logger = logging.getLogger(__name__)

# Ensure VADER lexicon is available
try:
    nltk.data.find("sentiment/vader_lexicon.zip")
except LookupError:
    nltk.download("vader_lexicon", quiet=True)

# Financial domain enhancements for VADER
FINANCIAL_LEXICON_UPDATES = {
    "bullish": 2.5,
    "bearish": -2.5,
    "rally": 2.0,
    "crash": -3.0,
    "correction": -1.5,
    "recession": -2.5,
    "recovery": 2.0,
    "hawkish": -1.0,  # negative for equities
    "dovish": 1.5,    # positive for equities
    "tightening": -1.5,
    "easing": 1.5,
    "inflation": -1.0,
    "deflation": -1.5,
    "overweight": 1.5,
    "underweight": -1.5,
    "upgrade": 2.0,
    "downgrade": -2.0,
    "outperform": 2.0,
    "underperform": -2.0,
    "default": -3.0,
    "bankruptcy": -3.5,
    "dividend": 1.0,
    "buyback": 1.5,
    "tariff": -1.5,
    "sanctions": -1.5,
    "stimulus": 2.0,
    "bubble": -2.0,
    "surge": 2.0,
    "plunge": -2.5,
    "soar": 2.5,
    "tumble": -2.0,
    "breakout": 1.5,
    "breakdown": -1.5,
}


def get_analyzer() -> SentimentIntensityAnalyzer:
    """Get a VADER analyzer with financial domain enhancements."""
    sia = SentimentIntensityAnalyzer()
    sia.lexicon.update(FINANCIAL_LEXICON_UPDATES)
    return sia


def score_sentiment(text: str) -> dict:
    """Score the sentiment of a text using VADER.

    Returns:
        {
            'compound': float,   # -1.0 to 1.0
            'positive': float,   # 0.0 to 1.0
            'negative': float,   # 0.0 to 1.0
            'neutral': float,    # 0.0 to 1.0
            'label': str,        # 'very_negative' .. 'very_positive'
        }
    """
    if not text:
        return {
            "compound": 0.0,
            "positive": 0.0,
            "negative": 0.0,
            "neutral": 1.0,
            "label": "neutral",
        }

    analyzer = get_analyzer()
    scores = analyzer.polarity_scores(text)
    compound = scores["compound"]

    # Determine label based on thresholds
    if compound <= SENTIMENT_THRESHOLDS["very_negative"]:
        label = "very_negative"
    elif compound <= SENTIMENT_THRESHOLDS["negative"]:
        label = "negative"
    elif compound <= SENTIMENT_THRESHOLDS["neutral_high"]:
        label = "neutral"
    elif compound <= SENTIMENT_THRESHOLDS["positive"]:
        label = "positive"
    else:
        label = "very_positive"

    return {
        "compound": compound,
        "positive": scores["pos"],
        "negative": scores["neg"],
        "neutral": scores["neu"],
        "label": label,
    }


def score_items(items: list[dict]) -> list[dict]:
    """Score sentiment for a list of items.

    Each item should have 'title' and optionally 'content'.
    Returns items enriched with 'sentiment_score' and 'sentiment_label'.
    """
    results = []
    for item in items:
        text = item.get("title", "") + " " + (item.get("content", "") or "")
        sentiment = score_sentiment(text)
        enriched = dict(item)
        enriched["sentiment_score"] = sentiment["compound"]
        enriched["sentiment_label"] = sentiment["label"]
        results.append(enriched)
    return results
