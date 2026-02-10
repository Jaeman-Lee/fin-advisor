"""Portfolio allocation engine.

Generates asset allocation recommendations based on signals,
risk assessment, trend analysis, and sentiment data.
"""

import json
import logging

from src.database.operations import DatabaseOperations
from src.database.queries import AnalyticalQueries
from src.analysis.risk_assessor import assess_market_risk
from src.analysis.trend_detector import get_all_trend_signals
from src.utils.config import ALLOCATION_BOUNDS

logger = logging.getLogger(__name__)


def compute_asset_type_scores(db: DatabaseOperations) -> dict[str, dict]:
    """Compute composite scores for each asset type based on multiple factors.

    Returns dict mapping asset_type -> {score, factors}.
    Score range: -1.0 (strongly underweight) to 1.0 (strongly overweight).
    """
    queries = AnalyticalQueries(db)
    risk_data = assess_market_risk(db)
    trend_signals = get_all_trend_signals(db)
    signals = queries.active_signals_summary()
    prices = queries.latest_prices()

    type_scores: dict[str, dict] = {
        "stock": {"score": 0.0, "factors": []},
        "bond": {"score": 0.0, "factors": []},
        "commodity": {"score": 0.0, "factors": []},
        "crypto": {"score": 0.0, "factors": []},
        "cash": {"score": 0.0, "factors": []},
    }

    # Factor 1: Trend signals
    trend_by_type: dict[str, list[str]] = {}
    for ticker, sigs in trend_signals.items():
        # Find asset type
        atype = None
        for p in prices:
            if p.get("ticker") == ticker:
                atype = p.get("asset_type")
                break
        if not atype or atype not in type_scores:
            continue
        trends = [s.get("value") or s.get("signal", "") for s in sigs
                  if s.get("type") in ("current_trend", "golden_cross", "death_cross")]
        trend_by_type.setdefault(atype, []).extend(trends)

    for atype, trends in trend_by_type.items():
        bullish = sum(1 for t in trends if t in ("strong_uptrend", "uptrend", "bullish"))
        bearish = sum(1 for t in trends if t in ("strong_downtrend", "downtrend", "bearish"))
        total = bullish + bearish
        if total > 0:
            trend_score = (bullish - bearish) / total * 0.3
            type_scores[atype]["score"] += trend_score
            type_scores[atype]["factors"].append(f"Trend: {bullish}B/{bearish}S -> {trend_score:+.2f}")

    # Factor 2: Risk level adjustment
    risk_by_type = risk_data.get("risk_by_type", {})
    for atype, rdata in risk_by_type.items():
        if atype not in type_scores:
            continue
        avg_risk = rdata.get("avg_risk", 0.5)
        # Higher risk -> slight underweight
        risk_adj = -(avg_risk - 0.5) * 0.2
        type_scores[atype]["score"] += risk_adj
        type_scores[atype]["factors"].append(f"Risk adj: {risk_adj:+.2f} (risk={avg_risk:.2f})")

    # Factor 3: Signal-based
    signal_by_type: dict[str, list[dict]] = {}
    for sig in signals:
        atype = sig.get("asset_type")
        if atype and atype in type_scores:
            signal_by_type.setdefault(atype, []).append(sig)

    for atype, sigs in signal_by_type.items():
        buy_strength = sum(s.get("strength", 0) for s in sigs if s.get("signal_type") in ("buy", "overweight"))
        sell_strength = sum(s.get("strength", 0) for s in sigs if s.get("signal_type") in ("sell", "underweight"))
        net = (buy_strength - sell_strength) * 0.2
        type_scores[atype]["score"] += net
        type_scores[atype]["factors"].append(f"Signals: {net:+.2f}")

    # Clamp scores
    for atype in type_scores:
        type_scores[atype]["score"] = max(-1.0, min(1.0, type_scores[atype]["score"]))

    return type_scores


def generate_allocation(db: DatabaseOperations, risk_tolerance: str = "moderate") -> dict:
    """Generate portfolio allocation recommendation.

    Args:
        db: Database operations instance.
        risk_tolerance: 'conservative', 'moderate', 'aggressive'

    Returns:
        {
            'allocation': {asset_type: weight_pct, ...},
            'rationale': {asset_type: str, ...},
            'risk_profile': str,
            'total_weight': 100.0,
        }
    """
    scores = compute_asset_type_scores(db)

    # Base allocation by risk tolerance
    base_allocations = {
        "conservative": {"stock": 25, "bond": 40, "commodity": 10, "crypto": 0, "cash": 25},
        "moderate":     {"stock": 40, "bond": 25, "commodity": 10, "crypto": 5, "cash": 20},
        "aggressive":   {"stock": 55, "bond": 10, "commodity": 10, "crypto": 15, "cash": 10},
    }
    base = base_allocations.get(risk_tolerance, base_allocations["moderate"])

    # Adjust based on scores
    allocation: dict[str, float] = {}
    rationale: dict[str, str] = {}

    for atype, base_weight in base.items():
        score_data = scores.get(atype, {"score": 0.0, "factors": []})
        score = score_data["score"]
        factors = score_data["factors"]

        # Adjust: ±15pp max based on score
        adjustment = score * 15
        raw_weight = base_weight + adjustment

        # Apply bounds
        bounds = ALLOCATION_BOUNDS.get(atype, (0.0, 1.0))
        weight = max(bounds[0] * 100, min(bounds[1] * 100, raw_weight))
        allocation[atype] = round(weight, 1)

        direction = "overweight" if adjustment > 0 else "underweight" if adjustment < 0 else "neutral"
        factor_str = "; ".join(factors) if factors else "No significant signals"
        rationale[atype] = f"{direction} ({adjustment:+.1f}pp). {factor_str}"

    # Normalize to 100%
    total = sum(allocation.values())
    if total > 0 and total != 100:
        factor = 100.0 / total
        for atype in allocation:
            allocation[atype] = round(allocation[atype] * factor, 1)

    return {
        "allocation": allocation,
        "rationale": rationale,
        "risk_profile": risk_tolerance,
        "total_weight": round(sum(allocation.values()), 1),
        "scores": {k: {"score": round(v["score"], 3), "factors": v["factors"]}
                   for k, v in scores.items()},
    }


def store_allocation_as_report(db: DatabaseOperations,
                               allocation_result: dict) -> int:
    """Store an allocation result as an advisory report."""
    signal_ids: list[int] = []
    active = db.get_active_signals()
    signal_ids = [s["id"] for s in active[:20]]

    return db.insert_report(
        report_type="adhoc",
        title=f"Asset Allocation - {allocation_result['risk_profile'].title()} Profile",
        executive_summary=_format_summary(allocation_result),
        market_overview=None,
        recommendations=allocation_result["allocation"],
        risk_assessment=json.dumps(allocation_result.get("scores", {})),
        signal_ids=signal_ids,
    )


def _format_summary(result: dict) -> str:
    """Format allocation result as human-readable summary."""
    lines = [f"Risk Profile: {result['risk_profile'].title()}\n"]
    lines.append("Recommended Allocation:")
    for atype, weight in sorted(result["allocation"].items(), key=lambda x: -x[1]):
        lines.append(f"  {atype.title():12s}: {weight:5.1f}%")
    lines.append(f"\nRationale:")
    for atype, rat in result["rationale"].items():
        lines.append(f"  {atype.title()}: {rat}")
    return "\n".join(lines)
