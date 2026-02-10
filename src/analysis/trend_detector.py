"""Trend detection and momentum analysis for market data."""

import logging

from src.database.operations import DatabaseOperations
from src.database.queries import AnalyticalQueries

logger = logging.getLogger(__name__)


def classify_trend(close: float | None, sma_20: float | None,
                   sma_50: float | None, sma_200: float | None) -> str:
    """Classify trend based on SMA alignment.

    Returns one of: 'strong_uptrend', 'uptrend', 'sideways', 'downtrend', 'strong_downtrend'
    """
    if not close or not sma_50:
        return "unknown"

    if sma_200 and sma_20:
        if close > sma_20 > sma_50 > sma_200:
            return "strong_uptrend"
        if close < sma_20 < sma_50 < sma_200:
            return "strong_downtrend"

    if close > sma_50:
        return "uptrend"
    elif close < sma_50:
        return "downtrend"
    return "sideways"


def detect_golden_death_cross(prices: list[dict]) -> list[dict]:
    """Detect golden cross (SMA50 crosses above SMA200) and death cross (opposite).

    Args:
        prices: List of market_data dicts ordered by date ascending.

    Returns:
        List of detected crossover events.
    """
    events: list[dict] = []
    if len(prices) < 2:
        return events

    for i in range(1, len(prices)):
        prev = prices[i - 1]
        curr = prices[i]

        prev_50 = prev.get("sma_50")
        prev_200 = prev.get("sma_200")
        curr_50 = curr.get("sma_50")
        curr_200 = curr.get("sma_200")

        if not all([prev_50, prev_200, curr_50, curr_200]):
            continue

        # Golden cross: SMA50 crosses above SMA200
        if prev_50 <= prev_200 and curr_50 > curr_200:
            events.append({
                "type": "golden_cross",
                "date": curr.get("date"),
                "sma_50": curr_50,
                "sma_200": curr_200,
                "signal": "bullish",
                "description": "SMA50 crossed above SMA200 (Golden Cross)",
            })
        # Death cross: SMA50 crosses below SMA200
        elif prev_50 >= prev_200 and curr_50 < curr_200:
            events.append({
                "type": "death_cross",
                "date": curr.get("date"),
                "sma_50": curr_50,
                "sma_200": curr_200,
                "signal": "bearish",
                "description": "SMA50 crossed below SMA200 (Death Cross)",
            })

    return events


def detect_macd_crossover(prices: list[dict]) -> list[dict]:
    """Detect MACD line crossing above/below signal line.

    Args:
        prices: List of market_data dicts ordered by date ascending.
    """
    events: list[dict] = []
    if len(prices) < 2:
        return events

    for i in range(1, len(prices)):
        prev = prices[i - 1]
        curr = prices[i]

        prev_macd = prev.get("macd")
        prev_signal = prev.get("macd_signal")
        curr_macd = curr.get("macd")
        curr_signal = curr.get("macd_signal")

        if not all([prev_macd, prev_signal, curr_macd, curr_signal]):
            continue

        if prev_macd <= prev_signal and curr_macd > curr_signal:
            events.append({
                "type": "macd_bullish_cross",
                "date": curr.get("date"),
                "macd": curr_macd,
                "signal_line": curr_signal,
                "signal": "bullish",
                "description": "MACD crossed above signal line",
            })
        elif prev_macd >= prev_signal and curr_macd < curr_signal:
            events.append({
                "type": "macd_bearish_cross",
                "date": curr.get("date"),
                "macd": curr_macd,
                "signal_line": curr_signal,
                "signal": "bearish",
                "description": "MACD crossed below signal line",
            })

    return events


def detect_bollinger_squeeze(prices: list[dict], bandwidth_threshold: float = 0.05) -> list[dict]:
    """Detect Bollinger Band squeezes (low volatility, potential breakout).

    Args:
        prices: Market data dicts ordered by date ascending.
        bandwidth_threshold: Bandwidth below this indicates squeeze.
    """
    events: list[dict] = []
    for row in prices:
        upper = row.get("bb_upper")
        lower = row.get("bb_lower")
        middle = row.get("bb_middle")

        if not all([upper, lower, middle]) or middle == 0:
            continue

        bandwidth = (upper - lower) / middle
        if bandwidth < bandwidth_threshold:
            events.append({
                "type": "bollinger_squeeze",
                "date": row.get("date"),
                "bandwidth": round(bandwidth, 4),
                "close": row.get("close"),
                "description": f"Bollinger Band squeeze detected (bandwidth={bandwidth:.4f})",
            })

    return events


def get_all_trend_signals(db: DatabaseOperations) -> dict[str, list[dict]]:
    """Get comprehensive trend signals for all assets.

    Returns dict mapping ticker -> list of trend signals.
    """
    assets = db.get_all_assets()
    all_signals: dict[str, list[dict]] = {}

    for asset in assets:
        asset_id = asset["id"]
        ticker = asset["ticker"]

        # Get price history (ascending order for crossover detection)
        prices = db.get_market_data(asset_id, limit=250)
        prices = prices[::-1]  # reverse to ascending

        if not prices:
            continue

        signals: list[dict] = []

        # Current trend
        latest = prices[-1] if prices else {}
        trend = classify_trend(
            latest.get("close"),
            latest.get("sma_20"),
            latest.get("sma_50"),
            latest.get("sma_200"),
        )
        if trend != "unknown":
            signals.append({"type": "current_trend", "value": trend, "date": latest.get("date")})

        # Crossovers (check last 20 data points)
        recent = prices[-20:] if len(prices) >= 20 else prices
        signals.extend(detect_golden_death_cross(recent))
        signals.extend(detect_macd_crossover(recent))
        signals.extend(detect_bollinger_squeeze(recent))

        if signals:
            all_signals[ticker] = signals

    return all_signals
