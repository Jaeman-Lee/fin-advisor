"""Cross-theme correlation analysis.

Identifies relationships and correlations between different themes
to surface non-obvious investment insights.
"""

import logging
from collections import defaultdict

from src.database.operations import DatabaseOperations
from src.database.queries import AnalyticalQueries

logger = logging.getLogger(__name__)


def compute_theme_sentiment_matrix(db: DatabaseOperations,
                                   days: int = 30) -> dict[str, dict]:
    """Compute sentiment matrix across themes.

    Returns dict mapping theme_category -> {avg_sentiment, avg_impact, count, trend_direction}
    """
    queries = AnalyticalQueries(db)
    data = queries.sentiment_summary(days=days)

    matrix: dict[str, dict] = {}
    for row in data:
        cat = row.get("category", "unknown")
        if cat not in matrix:
            matrix[cat] = {
                "avg_sentiment": 0.0,
                "avg_impact": 0.0,
                "total_items": 0,
                "bullish_count": 0,
                "bearish_count": 0,
                "themes": [],
            }
        matrix[cat]["total_items"] += row.get("item_count", 0)
        matrix[cat]["bullish_count"] += row.get("bullish_count", 0)
        matrix[cat]["bearish_count"] += row.get("bearish_count", 0)
        matrix[cat]["themes"].append({
            "name": row.get("theme_name"),
            "sentiment": row.get("avg_sentiment"),
            "impact": row.get("avg_impact"),
            "count": row.get("item_count"),
        })

    # Compute category-level averages
    for cat, data in matrix.items():
        themes = data["themes"]
        if themes:
            total_count = sum(t.get("count", 0) or 0 for t in themes)
            if total_count > 0:
                data["avg_sentiment"] = sum(
                    (t.get("sentiment", 0) or 0) * (t.get("count", 0) or 0) for t in themes
                ) / total_count
                data["avg_impact"] = sum(
                    (t.get("impact", 0) or 0) * (t.get("count", 0) or 0) for t in themes
                ) / total_count

    return matrix


def detect_theme_divergences(db: DatabaseOperations, days: int = 30) -> list[dict]:
    """Detect divergences between themes that usually correlate.

    For example: macro sentiment bullish but technical signals bearish.
    """
    matrix = compute_theme_sentiment_matrix(db, days)
    divergences: list[dict] = []

    # Expected correlations
    correlation_pairs = [
        ("macro", "asset"),       # Macro outlook should align with asset sentiment
        ("sentiment", "technical"),  # Market sentiment should align with technicals
        ("geopolitics", "asset"),  # Geopolitical risk should impact assets
    ]

    for theme_a, theme_b in correlation_pairs:
        if theme_a not in matrix or theme_b not in matrix:
            continue

        sent_a = matrix[theme_a]["avg_sentiment"]
        sent_b = matrix[theme_b]["avg_sentiment"]

        # Divergence if sentiments are in opposite directions with significant magnitude
        if sent_a * sent_b < 0 and (abs(sent_a) > 0.1 and abs(sent_b) > 0.1):
            divergences.append({
                "theme_a": theme_a,
                "theme_b": theme_b,
                "sentiment_a": round(sent_a, 3),
                "sentiment_b": round(sent_b, 3),
                "divergence_magnitude": round(abs(sent_a - sent_b), 3),
                "interpretation": _interpret_divergence(theme_a, sent_a, theme_b, sent_b),
            })

    return divergences


def _interpret_divergence(theme_a: str, sent_a: float,
                          theme_b: str, sent_b: float) -> str:
    """Generate human-readable interpretation of a theme divergence."""
    dir_a = "bullish" if sent_a > 0 else "bearish"
    dir_b = "bullish" if sent_b > 0 else "bearish"
    return (
        f"{theme_a.title()} sentiment is {dir_a} ({sent_a:+.3f}) while "
        f"{theme_b.title()} sentiment is {dir_b} ({sent_b:+.3f}). "
        f"This divergence may indicate a market turning point or lagging adjustment."
    )


def cross_asset_correlation_signals(db: DatabaseOperations) -> list[dict]:
    """Identify cross-asset signals from correlated movements.

    Looks for unusual divergences in typically correlated assets.
    """
    queries = AnalyticalQueries(db)
    prices = queries.latest_prices()

    # Group by asset type
    by_type: dict[str, list[dict]] = defaultdict(list)
    for p in prices:
        by_type[p.get("asset_type", "unknown")].append(p)

    signals: list[dict] = []

    # Check for gold/bond correlation signal
    # Gold and bonds typically move together (risk-off trade)
    gold_rsi = None
    bond_rsi = None
    for p in by_type.get("commodity", []):
        if p.get("ticker") == "GC=F":
            gold_rsi = p.get("rsi_14")
    for p in by_type.get("bond", []):
        if p.get("ticker") == "TLT":
            bond_rsi = p.get("rsi_14")

    if gold_rsi and bond_rsi:
        if abs(gold_rsi - bond_rsi) > 25:
            signals.append({
                "type": "cross_asset_divergence",
                "assets": ["GC=F", "TLT"],
                "description": f"Gold RSI ({gold_rsi:.1f}) diverging from Bond RSI ({bond_rsi:.1f})",
                "implication": "Safe-haven divergence may indicate shifting risk preferences",
            })

    return signals
