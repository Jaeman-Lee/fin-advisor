"""Technical indicator calculations: RSI, MACD, Bollinger Bands, SMA."""

import logging

import pandas as pd
import pandas_ta as ta

from src.database.operations import DatabaseOperations
from src.utils.config import (
    BOLLINGER_PERIOD,
    BOLLINGER_STD,
    MACD_FAST,
    MACD_SIGNAL,
    MACD_SLOW,
    RSI_PERIOD,
    SMA_PERIODS,
)

logger = logging.getLogger(__name__)


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all technical indicators on a DataFrame with 'close' column.

    Input must have columns: close (and optionally high, low, volume).
    Returns DataFrame with additional indicator columns.
    """
    if df.empty or "close" not in df.columns:
        return df

    result = df.copy()

    # SMA
    for period in SMA_PERIODS:
        col = f"sma_{period}"
        result[col] = ta.sma(result["close"], length=period)

    # RSI
    result["rsi_14"] = ta.rsi(result["close"], length=RSI_PERIOD)

    # MACD (requires at least MACD_SLOW + MACD_SIGNAL data points)
    if len(result) >= MACD_SLOW + MACD_SIGNAL:
        try:
            macd_result = ta.macd(result["close"],
                                  fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL)
            if macd_result is not None and not macd_result.empty:
                result["macd"] = macd_result.iloc[:, 0]
                result["macd_hist"] = macd_result.iloc[:, 1]
                result["macd_signal"] = macd_result.iloc[:, 2]
        except Exception as e:
            logger.warning(f"MACD computation failed: {e}")

    # Bollinger Bands
    if len(result) >= BOLLINGER_PERIOD:
        try:
            bb = ta.bbands(result["close"], length=BOLLINGER_PERIOD, std=BOLLINGER_STD)
            if bb is not None and not bb.empty:
                result["bb_lower"] = bb.iloc[:, 0]
                result["bb_middle"] = bb.iloc[:, 1]
                result["bb_upper"] = bb.iloc[:, 2]
        except Exception as e:
            logger.warning(f"Bollinger Bands computation failed: {e}")

    return result


def update_indicators_in_db(db: DatabaseOperations, asset_id: int) -> int:
    """Fetch market data for an asset, compute indicators, and update DB.

    Returns number of rows updated.
    """
    rows = db.get_market_data(asset_id, limit=1000)
    if not rows:
        return 0

    # Build DataFrame (rows come DESC, reverse for chronological)
    df = pd.DataFrame(rows[::-1])

    # Compute indicators
    df = compute_indicators(df)

    # Update DB
    indicator_cols = [
        "sma_20", "sma_50", "sma_200", "rsi_14",
        "macd", "macd_signal", "macd_hist",
        "bb_upper", "bb_middle", "bb_lower",
    ]

    count = 0
    for _, row in df.iterrows():
        updates = {}
        for col in indicator_cols:
            if col in row and pd.notna(row[col]):
                updates[col] = float(row[col])
        if updates:
            db.update_technical_indicators(asset_id, row["date"], **updates)
            count += 1

    logger.info(f"Updated {count} rows with indicators for asset_id={asset_id}")
    return count
