"""FRED (Federal Reserve Economic Data) macro indicator collection."""

import logging
from datetime import datetime, timedelta

import requests

from src.database.operations import DatabaseOperations
from src.utils.config import (
    FRED_API_KEY,
    FRED_BASE_URL,
    FRED_DEFAULT_LOOKBACK_YEARS,
    FRED_SERIES,
)

logger = logging.getLogger(__name__)


def fetch_fred_series(
    series_id: str,
    api_key: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Fetch observations for a FRED series.

    Returns list of {'date': 'YYYY-MM-DD', 'value': float|None}.
    """
    key = api_key or FRED_API_KEY
    if not key:
        raise ValueError(
            "FRED API key required. Set FRED_API_KEY env var or pass api_key param. "
            "Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html"
        )

    url = f"{FRED_BASE_URL}/series/observations"
    params = {
        "series_id": series_id,
        "api_key": key,
        "file_type": "json",
    }
    if start_date:
        params["observation_start"] = start_date
    if end_date:
        params["observation_end"] = end_date

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    observations = []
    for obs in data.get("observations", []):
        val = obs.get("value", ".")
        observations.append({
            "date": obs["date"],
            "value": float(val) if val not in (".", "") else None,
        })
    return observations


def collect_fred_series(
    db: DatabaseOperations,
    series_id: str,
    api_key: str | None = None,
    lookback_years: int | None = None,
) -> int:
    """Collect a single FRED series and store in DB.

    Returns count of rows upserted.
    """
    years = lookback_years or FRED_DEFAULT_LOOKBACK_YEARS
    start = (datetime.now() - timedelta(days=years * 365)).strftime("%Y-%m-%d")

    meta = FRED_SERIES.get(series_id)
    name = meta[0] if meta else series_id
    logger.info(f"  Fetching {series_id} ({name})...")

    try:
        observations = fetch_fred_series(
            series_id, api_key=api_key, start_date=start,
        )
    except requests.RequestException as e:
        logger.error(f"  Failed to fetch {series_id}: {e}")
        return 0

    count = 0
    for obs in observations:
        db.upsert_macro_indicator(series_id, obs["date"], obs["value"])
        count += 1

    logger.info(f"  {series_id}: {count} observations stored")
    return count


def collect_all_fred(
    db: DatabaseOperations,
    series_ids: list[str] | None = None,
    category: str | None = None,
    api_key: str | None = None,
    lookback_years: int | None = None,
) -> dict[str, int]:
    """Collect multiple FRED series.

    Args:
        series_ids: specific series to collect (default: all in FRED_SERIES)
        category: filter by category (e.g. 'inflation', 'employment')
        api_key: FRED API key override
        lookback_years: how far back to fetch

    Returns dict: series_id -> count of rows.
    """
    if series_ids:
        targets = series_ids
    elif category:
        targets = [
            sid for sid, (_, cat, _) in FRED_SERIES.items()
            if cat == category
        ]
    else:
        targets = list(FRED_SERIES.keys())

    logger.info(f"Collecting {len(targets)} FRED series...")
    results: dict[str, int] = {}
    for sid in targets:
        results[sid] = collect_fred_series(
            db, sid, api_key=api_key, lookback_years=lookback_years,
        )
    total = sum(results.values())
    success = sum(1 for v in results.values() if v > 0)
    logger.info(f"FRED collection complete: {total} rows for {success}/{len(targets)} series")
    return results


def get_macro_dashboard(db: DatabaseOperations) -> dict:
    """Build a macro indicator dashboard from latest FRED values.

    Returns structured dict grouped by category.
    """
    snapshot = db.get_macro_snapshot()
    by_series = {row["series_id"]: row for row in snapshot}

    dashboard: dict[str, list[dict]] = {}
    for sid, (name, category, freq) in FRED_SERIES.items():
        row = by_series.get(sid)
        entry = {
            "series_id": sid,
            "name": name,
            "frequency": freq,
            "value": row["value"] if row else None,
            "date": row["date"] if row else None,
        }
        dashboard.setdefault(category, []).append(entry)
    return dashboard


def get_yield_spread(db: DatabaseOperations) -> dict:
    """Get current yield curve spread data from FRED series."""
    spreads = {}
    for sid in ("T10Y2Y", "T10Y3M"):
        latest = db.get_latest_macro_value(sid)
        if latest:
            spreads[sid] = {
                "value": latest["value"],
                "date": latest["date"],
                "inverted": latest["value"] < 0 if latest["value"] is not None else None,
            }
    return spreads


def get_inflation_trend(db: DatabaseOperations, months: int = 12) -> dict:
    """Get recent CPI/PCE trend."""
    result = {}
    for sid in ("CPIAUCSL", "CPILFESL", "PCEPILFE"):
        rows = db.get_macro_series(sid, limit=months + 1)
        if len(rows) < 2:
            continue
        # rows are DESC order; compute YoY if we have 12+ months
        latest = rows[0]
        result[sid] = {
            "name": FRED_SERIES[sid][0],
            "latest_value": latest["value"],
            "latest_date": latest["date"],
        }
        if len(rows) > 12 and latest["value"] and rows[12]["value"]:
            yoy = ((latest["value"] - rows[12]["value"]) / rows[12]["value"]) * 100
            result[sid]["yoy_pct"] = round(yoy, 2)
    return result
