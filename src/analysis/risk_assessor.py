"""Risk assessment module for portfolio and market risk evaluation."""

import logging
import math

from src.database.operations import DatabaseOperations
from src.database.queries import AnalyticalQueries
from src.utils.config import RISK_LEVELS

logger = logging.getLogger(__name__)


def compute_volatility(prices: list[dict], window: int = 20) -> float | None:
    """Compute annualized volatility from price data.

    Args:
        prices: List of market_data dicts with 'close' field, date-ascending.
        window: Rolling window for volatility calculation.

    Returns:
        Annualized volatility as a decimal (e.g., 0.25 = 25%).
    """
    closes = [p["close"] for p in prices if p.get("close")]
    if len(closes) < window + 1:
        return None

    # Daily returns
    returns = [(closes[i] - closes[i - 1]) / closes[i - 1]
               for i in range(1, len(closes)) if closes[i - 1] != 0]

    if len(returns) < window:
        return None

    # Use most recent window
    recent = returns[-window:]
    mean = sum(recent) / len(recent)
    variance = sum((r - mean) ** 2 for r in recent) / (len(recent) - 1)
    daily_vol = math.sqrt(variance)
    annualized = daily_vol * math.sqrt(252)  # trading days
    return round(annualized, 4)


def compute_max_drawdown(prices: list[dict]) -> dict:
    """Compute maximum drawdown from price data.

    Args:
        prices: List of dicts with 'close' and 'date', date-ascending.

    Returns:
        {'max_drawdown': float, 'peak_date': str, 'trough_date': str}
    """
    closes = [(p.get("date", ""), p["close"]) for p in prices if p.get("close")]
    if len(closes) < 2:
        return {"max_drawdown": 0.0, "peak_date": "", "trough_date": ""}

    max_dd = 0.0
    peak_val = closes[0][1]
    peak_date = closes[0][0]
    dd_peak_date = peak_date
    dd_trough_date = peak_date

    for date, close in closes:
        if close > peak_val:
            peak_val = close
            peak_date = date
        dd = (peak_val - close) / peak_val if peak_val > 0 else 0
        if dd > max_dd:
            max_dd = dd
            dd_peak_date = peak_date
            dd_trough_date = date

    return {
        "max_drawdown": round(max_dd, 4),
        "peak_date": dd_peak_date,
        "trough_date": dd_trough_date,
    }


def classify_risk_level(score: float) -> str:
    """Classify a risk score (0-1) into a risk level label."""
    for level, (low, high) in RISK_LEVELS.items():
        if low <= score < high:
            return level
    return "very_high"


def assess_asset_risk(db: DatabaseOperations, asset_id: int) -> dict:
    """Assess risk for a single asset.

    Returns comprehensive risk assessment dict.
    """
    prices = db.get_market_data(asset_id, limit=300)
    prices = prices[::-1]  # ascending

    if not prices:
        return {"asset_id": asset_id, "risk_level": "unknown", "risk_score": None}

    latest = prices[-1]
    volatility = compute_volatility(prices)
    drawdown = compute_max_drawdown(prices)
    rsi = latest.get("rsi_14")

    # Composite risk score (0 to 1, higher = more risky)
    risk_components: list[float] = []

    if volatility is not None:
        # Map volatility to 0-1 (assuming 0-60% range)
        vol_risk = min(volatility / 0.60, 1.0)
        risk_components.append(vol_risk)

    if drawdown["max_drawdown"] > 0:
        dd_risk = min(drawdown["max_drawdown"] / 0.50, 1.0)
        risk_components.append(dd_risk)

    if rsi is not None:
        # Extreme RSI values indicate higher risk
        rsi_risk = max(abs(rsi - 50) - 10, 0) / 40
        risk_components.append(min(rsi_risk, 1.0))

    risk_score = sum(risk_components) / len(risk_components) if risk_components else 0.5

    return {
        "asset_id": asset_id,
        "volatility_annualized": volatility,
        "max_drawdown": drawdown["max_drawdown"],
        "drawdown_peak": drawdown["peak_date"],
        "drawdown_trough": drawdown["trough_date"],
        "current_rsi": rsi,
        "risk_score": round(risk_score, 3),
        "risk_level": classify_risk_level(risk_score),
    }


def assess_market_risk(db: DatabaseOperations) -> dict:
    """Assess overall market risk across all tracked assets.

    Returns market-level risk summary.
    """
    assets = db.get_all_assets()
    if not assets:
        return {"overall_risk": "unknown", "risk_score": None, "assets": []}

    asset_risks: list[dict] = []
    for asset in assets:
        risk = assess_asset_risk(db, asset["id"])
        risk["ticker"] = asset["ticker"]
        risk["name"] = asset["name"]
        risk["asset_type"] = asset["asset_type"]
        asset_risks.append(risk)

    # Filter assets with valid risk scores
    valid_risks = [r for r in asset_risks if r.get("risk_score") is not None]

    if not valid_risks:
        return {"overall_risk": "unknown", "risk_score": None, "assets": asset_risks}

    avg_risk = sum(r["risk_score"] for r in valid_risks) / len(valid_risks)

    # Find highest risk assets
    high_risk = sorted(valid_risks, key=lambda r: r["risk_score"], reverse=True)[:5]

    return {
        "overall_risk": classify_risk_level(avg_risk),
        "risk_score": round(avg_risk, 3),
        "total_assets_assessed": len(valid_risks),
        "high_risk_assets": high_risk,
        "risk_by_type": _risk_by_asset_type(valid_risks),
    }


def _risk_by_asset_type(risks: list[dict]) -> dict:
    """Group average risk by asset type."""
    from collections import defaultdict
    groups: dict[str, list[float]] = defaultdict(list)
    for r in risks:
        atype = r.get("asset_type", "unknown")
        if r.get("risk_score") is not None:
            groups[atype].append(r["risk_score"])

    return {
        atype: {
            "avg_risk": round(sum(scores) / len(scores), 3),
            "risk_level": classify_risk_level(sum(scores) / len(scores)),
            "count": len(scores),
        }
        for atype, scores in groups.items()
    }
