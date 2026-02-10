"""yfinance wrapper for fetching market data (stocks, bonds, commodities, FX)."""

import logging
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from src.database.operations import DatabaseOperations
from src.utils.config import (
    ALL_TICKERS,
    ASSET_TYPE_MAP,
    DEFAULT_LOOKBACK_DAYS,
    MARKET_DATA_INTERVAL,
)

logger = logging.getLogger(__name__)


def _safe_float(val) -> float | None:
    """Convert a value to float, returning None for NaN/None."""
    if val is None:
        return None
    try:
        import math
        f = float(val)
        return None if math.isnan(f) else f
    except (ValueError, TypeError):
        return None


def fetch_ticker_info(ticker: str) -> dict:
    """Fetch basic info for a ticker."""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        return {
            "ticker": ticker,
            "name": info.get("shortName") or info.get("longName") or ticker,
            "exchange": info.get("exchange", ""),
            "currency": info.get("currency", "USD"),
        }
    except Exception as e:
        logger.warning(f"Failed to fetch info for {ticker}: {e}")
        return {
            "ticker": ticker,
            "name": ticker,
            "exchange": "",
            "currency": "USD",
        }


def fetch_ohlcv(ticker: str, period_days: int = DEFAULT_LOOKBACK_DAYS,
                interval: str = MARKET_DATA_INTERVAL) -> pd.DataFrame:
    """Fetch OHLCV data for a single ticker.

    Returns DataFrame with columns: Date, Open, High, Low, Close, Volume, Adj Close
    """
    try:
        t = yf.Ticker(ticker)
        end = datetime.now()
        start = end - timedelta(days=period_days)
        df = t.history(start=start.strftime("%Y-%m-%d"),
                       end=end.strftime("%Y-%m-%d"),
                       interval=interval)
        if df.empty:
            logger.warning(f"No data returned for {ticker}")
            return pd.DataFrame()

        df = df.reset_index()
        # Normalize column names
        df.columns = [c.replace(" ", "_") for c in df.columns]
        return df
    except Exception as e:
        logger.error(f"Failed to fetch OHLCV for {ticker}: {e}")
        return pd.DataFrame()


def register_asset(db: DatabaseOperations, ticker: str,
                   asset_type: str | None = None) -> int:
    """Register an asset in the database, fetching info from yfinance."""
    atype = asset_type or ASSET_TYPE_MAP.get(ticker, "stock")
    info = fetch_ticker_info(ticker)
    return db.upsert_asset(
        ticker=ticker,
        name=info["name"],
        asset_type=atype,
        exchange=info.get("exchange"),
        currency=info.get("currency", "USD"),
    )


def collect_market_data(db: DatabaseOperations,
                        tickers: list[str] | None = None,
                        period_days: int = DEFAULT_LOOKBACK_DAYS,
                        interval: str = MARKET_DATA_INTERVAL) -> dict[str, int]:
    """Collect OHLCV data for all tickers and store in DB.

    Returns dict mapping ticker -> number of rows inserted/updated.
    """
    tickers = tickers or ALL_TICKERS
    results: dict[str, int] = {}

    for ticker in tickers:
        logger.info(f"Collecting data for {ticker}...")
        try:
            # Register asset
            asset_id = register_asset(db, ticker)

            # Fetch OHLCV
            df = fetch_ohlcv(ticker, period_days, interval)
            if df.empty:
                results[ticker] = 0
                continue

            count = 0
            date_col = "Date" if "Date" in df.columns else "Datetime" if "Datetime" in df.columns else df.columns[0]
            for _, row in df.iterrows():
                date_val = row[date_col]
                if hasattr(date_val, "strftime"):
                    date_str = date_val.strftime("%Y-%m-%d")
                else:
                    date_str = str(date_val)[:10]

                db.upsert_market_data(
                    asset_id=asset_id,
                    date=date_str,
                    open_=_safe_float(row.get("Open")),
                    high=_safe_float(row.get("High")),
                    low=_safe_float(row.get("Low")),
                    close=_safe_float(row.get("Close")),
                    volume=_safe_float(row.get("Volume")),
                    adj_close=_safe_float(row.get("Close")),  # yfinance already adjusts
                )
                count += 1
            results[ticker] = count
            logger.info(f"  {ticker}: {count} rows")
        except Exception as e:
            logger.error(f"  Failed for {ticker}: {e}")
            results[ticker] = 0

    return results
