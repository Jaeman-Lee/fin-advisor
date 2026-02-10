"""Macro economic data collection: treasury yields, commodities, FX rates."""

import logging

from src.collection.market_data import collect_market_data, register_asset
from src.database.operations import DatabaseOperations
from src.utils.config import BOND_TICKERS, COMMODITY_TICKERS, FX_TICKERS

logger = logging.getLogger(__name__)


def collect_bond_data(db: DatabaseOperations, period_days: int = 365) -> dict[str, int]:
    """Collect bond/treasury yield data."""
    logger.info("Collecting bond/treasury data...")
    return collect_market_data(db, tickers=BOND_TICKERS, period_days=period_days)


def collect_commodity_data(db: DatabaseOperations, period_days: int = 365) -> dict[str, int]:
    """Collect commodity futures data."""
    logger.info("Collecting commodity data...")
    return collect_market_data(db, tickers=COMMODITY_TICKERS, period_days=period_days)


def collect_fx_data(db: DatabaseOperations, period_days: int = 365) -> dict[str, int]:
    """Collect FX rate data."""
    logger.info("Collecting FX data...")
    return collect_market_data(db, tickers=FX_TICKERS, period_days=period_days)


def collect_all_macro(db: DatabaseOperations, period_days: int = 365) -> dict[str, int]:
    """Collect all macro data (bonds + commodities + FX)."""
    results: dict[str, int] = {}
    results.update(collect_bond_data(db, period_days))
    results.update(collect_commodity_data(db, period_days))
    results.update(collect_fx_data(db, period_days))
    return results


def get_yield_curve_snapshot(db: DatabaseOperations) -> dict[str, float | None]:
    """Get latest yield values for key maturities.

    Returns dict like {'3m': 5.23, '5y': 4.15, '10y': 4.35, '30y': 4.55}
    """
    ticker_map = {
        "^IRX": "3m",
        "^FVX": "5y",
        "^TNX": "10y",
        "^TYX": "30y",
    }
    snapshot: dict[str, float | None] = {}
    for ticker, label in ticker_map.items():
        asset_id = db.get_asset_id(ticker)
        if asset_id is None:
            snapshot[label] = None
            continue
        rows = db.get_market_data(asset_id, limit=1)
        if rows:
            snapshot[label] = rows[0].get("close")
        else:
            snapshot[label] = None
    return snapshot


def is_yield_curve_inverted(db: DatabaseOperations) -> bool | None:
    """Check if the yield curve is inverted (2y/10y spread negative).

    Uses 3m vs 10y as proxy since we track ^IRX and ^TNX.
    """
    snapshot = get_yield_curve_snapshot(db)
    short = snapshot.get("3m")
    long = snapshot.get("10y")
    if short is None or long is None:
        return None
    return short > long
