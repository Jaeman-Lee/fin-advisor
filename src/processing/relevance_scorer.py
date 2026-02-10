"""Relevance scoring for data items against tracked assets and themes."""

import json
import logging
import re

from src.database.operations import DatabaseOperations
from src.utils.config import ALL_TICKERS, RELEVANCE_MIN_SCORE

logger = logging.getLogger(__name__)

# Asset name patterns for text matching
ASSET_NAME_PATTERNS = {
    "AAPL": ["apple", "aapl", "iphone"],
    "MSFT": ["microsoft", "msft", "azure", "windows"],
    "GOOGL": ["google", "googl", "alphabet", "android"],
    "AMZN": ["amazon", "amzn", "aws"],
    "NVDA": ["nvidia", "nvda", "gpu", "cuda"],
    "TSLA": ["tesla", "tsla", "ev", "musk"],
    "005930.KS": ["samsung", "삼성전자", "galaxy"],
    "000660.KS": ["sk hynix", "hynix", "sk하이닉스"],
    "BTC-USD": ["bitcoin", "btc"],
    "ETH-USD": ["ethereum", "eth"],
    "SOL-USD": ["solana", "sol"],
    "GC=F": ["gold", "gold price", "xau"],
    "CL=F": ["crude oil", "wti", "oil price"],
    "BZ=F": ["brent crude", "brent"],
}

# Theme relevance keywords (broader than exact theme keywords)
THEME_RELEVANCE = {
    "macro": ["economy", "gdp", "employment", "jobs", "fed", "ecb", "central bank",
              "rate", "inflation", "cpi", "ppi", "fiscal"],
    "geopolitics": ["war", "conflict", "sanctions", "tariff", "trade", "tension",
                    "geopolit", "nato", "un ", "g7", "g20"],
    "sector": ["ai ", "semiconductor", "chip", "energy", "biotech", "pharma",
               "fintech", "cloud", "ev ", "battery", "renewable"],
    "asset": ["stock", "bond", "treasury", "yield", "commodity", "gold", "oil",
              "crypto", "bitcoin", "equity", "fixed income"],
    "sentiment": ["fear", "greed", "vix", "volatil", "panic", "euphoria",
                  "bull", "bear", "risk-on", "risk-off"],
    "technical": ["support", "resistance", "breakout", "trend", "moving average",
                  "rsi", "macd", "overbought", "oversold"],
}


def compute_relevance(title: str, content: str | None = None) -> dict:
    """Compute relevance scores for a text item.

    Returns:
        {
            'overall_score': float (0-1),
            'affected_assets': list[str],
            'primary_theme': str | None,
            'theme_scores': dict[str, float],
        }
    """
    text = (title + " " + (content or "")).lower()

    # 1. Find affected assets
    affected_assets: list[str] = []
    asset_score = 0.0
    for ticker, patterns in ASSET_NAME_PATTERNS.items():
        for pattern in patterns:
            if pattern in text:
                if ticker not in affected_assets:
                    affected_assets.append(ticker)
                asset_score += 0.15
                break

    # 2. Score theme relevance
    theme_scores: dict[str, float] = {}
    for theme, keywords in THEME_RELEVANCE.items():
        matches = sum(1 for kw in keywords if kw in text)
        if matches > 0:
            theme_scores[theme] = min(matches / len(keywords) * 3, 1.0)  # scale up

    # 3. Overall score
    theme_max = max(theme_scores.values()) if theme_scores else 0.0
    overall = min(asset_score * 0.4 + theme_max * 0.6, 1.0)

    # If no assets found but theme is relevant, still give minimum score
    if not affected_assets and theme_max > 0.3:
        overall = max(overall, 0.3)

    primary_theme = max(theme_scores, key=theme_scores.get) if theme_scores else None

    return {
        "overall_score": round(overall, 3),
        "affected_assets": affected_assets,
        "primary_theme": primary_theme,
        "theme_scores": {k: round(v, 3) for k, v in theme_scores.items()},
    }


def compute_impact_score(sentiment_score: float, relevance_score: float) -> float:
    """Compute impact score combining sentiment and relevance.

    Impact = sentiment_direction * relevance_weight
    Range: -1.0 (strong bearish) to 1.0 (strong bullish)
    """
    return round(sentiment_score * relevance_score, 3)


def score_and_filter(items: list[dict],
                     min_relevance: float = RELEVANCE_MIN_SCORE) -> list[dict]:
    """Score relevance for items and filter by minimum threshold.

    Each item should have 'title' and optionally 'content'.
    Returns items enriched with relevance data, filtered by min score.
    """
    results = []
    for item in items:
        relevance = compute_relevance(item.get("title", ""), item.get("content"))
        if relevance["overall_score"] >= min_relevance:
            enriched = dict(item)
            enriched["relevance_score"] = relevance["overall_score"]
            enriched["affected_assets"] = relevance["affected_assets"]
            enriched["primary_theme"] = relevance["primary_theme"]
            results.append(enriched)
    return results
