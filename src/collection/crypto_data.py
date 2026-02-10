"""Cryptocurrency data collection via yfinance."""

import logging

from src.collection.market_data import collect_market_data
from src.database.operations import DatabaseOperations
from src.utils.config import CRYPTO_TICKERS

logger = logging.getLogger(__name__)


def collect_crypto_data(db: DatabaseOperations,
                        tickers: list[str] | None = None,
                        period_days: int = 365) -> dict[str, int]:
    """Collect crypto OHLCV data."""
    tickers = tickers or CRYPTO_TICKERS
    logger.info(f"Collecting crypto data for {len(tickers)} tokens...")
    return collect_market_data(db, tickers=tickers, period_days=period_days)


def get_crypto_dominance(db: DatabaseOperations) -> dict[str, float]:
    """Estimate relative crypto market cap dominance from latest prices.

    This is an approximation using price * typical supply estimates.
    """
    # Rough circulating supply estimates (updated periodically)
    supply_estimates = {
        "BTC-USD": 19_600_000,
        "ETH-USD": 120_000_000,
        "SOL-USD": 440_000_000,
        "XRP-USD": 55_000_000_000,
        "ADA-USD": 36_000_000_000,
    }

    market_caps: dict[str, float] = {}
    for ticker, supply in supply_estimates.items():
        asset_id = db.get_asset_id(ticker)
        if asset_id is None:
            continue
        rows = db.get_market_data(asset_id, limit=1)
        if rows and rows[0].get("close"):
            market_caps[ticker] = rows[0]["close"] * supply

    total = sum(market_caps.values())
    if total == 0:
        return {}
    return {t: mc / total for t, mc in market_caps.items()}


def get_btc_fear_indicator(db: DatabaseOperations) -> dict:
    """Simple BTC momentum-based fear/greed proxy.

    Uses RSI and price vs SMA-200 to estimate market sentiment.
    """
    asset_id = db.get_asset_id("BTC-USD")
    if asset_id is None:
        return {"indicator": "unknown", "score": None}

    rows = db.get_market_data(asset_id, limit=1)
    if not rows:
        return {"indicator": "unknown", "score": None}

    latest = rows[0]
    rsi = latest.get("rsi_14")
    close = latest.get("close")
    sma200 = latest.get("sma_200")

    score = 50.0  # neutral default
    if rsi is not None:
        # RSI contribution (40% weight)
        score = rsi * 0.4 + score * 0.6

    if close is not None and sma200 is not None and sma200 > 0:
        # Price vs SMA-200 contribution
        ratio = close / sma200
        price_score = min(max((ratio - 0.7) / 0.6 * 100, 0), 100)
        score = score * 0.6 + price_score * 0.4

    if score < 25:
        label = "Extreme Fear"
    elif score < 40:
        label = "Fear"
    elif score < 60:
        label = "Neutral"
    elif score < 75:
        label = "Greed"
    else:
        label = "Extreme Greed"

    return {"indicator": label, "score": round(score, 1)}
