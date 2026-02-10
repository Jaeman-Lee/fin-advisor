"""News collection and structuring for the investment advisory system.

This module structures news data for storage. Actual web search is performed
by the info-collector agent using Claude's WebSearch tool. This module provides
utilities for structuring and storing the results.
"""

import hashlib
import json
import logging
from datetime import datetime

from src.database.operations import DatabaseOperations
from src.utils.config import NEWS_MAX_ITEMS_PER_QUERY

logger = logging.getLogger(__name__)

# Search queries organized by theme
NEWS_SEARCH_QUERIES = {
    "macro": [
        "Federal Reserve interest rate decision 2026",
        "US inflation CPI latest data",
        "global GDP growth forecast",
        "central bank monetary policy",
    ],
    "geopolitics": [
        "US China trade relations tariffs",
        "Middle East conflict oil supply impact",
        "global geopolitical risk markets",
    ],
    "sector": [
        "AI semiconductor industry outlook",
        "energy transition renewable investment",
        "biotech pharma FDA approval",
    ],
    "asset": [
        "stock market outlook forecast",
        "bond market treasury yield analysis",
        "gold commodity price forecast",
        "cryptocurrency bitcoin market analysis",
    ],
    "sentiment": [
        "market volatility VIX fear index",
        "investor sentiment survey",
    ],
}


def compute_content_hash(title: str, content: str | None = None) -> str:
    """Compute SHA-256 hash for deduplication."""
    text = title + (content or "")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def structure_search_result(result: dict) -> dict:
    """Structure a raw search result into our standard format.

    Expected input keys: title, snippet/description, url, date/published
    Returns standardized dict for database insertion.
    """
    title = result.get("title", "Untitled")
    content = result.get("snippet") or result.get("description") or ""
    url = result.get("url") or result.get("link") or ""
    published = result.get("date") or result.get("published") or ""

    return {
        "title": title,
        "content": content,
        "url": url,
        "published_at": published,
        "data_type": "news",
        "content_hash": compute_content_hash(title, content),
        "raw_json": json.dumps(result),
    }


def store_news_items(db: DatabaseOperations,
                     items: list[dict],
                     source_name: str = "websearch") -> list[int]:
    """Store structured news items in the database.

    Args:
        db: Database operations instance.
        items: List of structured items from structure_search_result().
        source_name: Name of the data source.

    Returns:
        List of inserted row IDs (skips duplicates).
    """
    source_id = db.get_source_id(source_name)
    if source_id is None:
        source_id = db.upsert_data_source(source_name, "news", "Web search results")

    inserted_ids: list[int] = []
    for item in items:
        # Skip duplicates
        if item.get("content_hash") and db.check_hash_exists(item["content_hash"]):
            logger.debug(f"Skipping duplicate: {item['title'][:50]}")
            continue

        row_id = db.insert_raw_item(
            source_id=source_id,
            title=item["title"],
            content=item.get("content"),
            url=item.get("url"),
            published_at=item.get("published_at"),
            data_type=item.get("data_type", "news"),
            raw_json=item.get("raw_json"),
            content_hash=item.get("content_hash"),
        )
        inserted_ids.append(row_id)
        logger.info(f"Stored news item: {item['title'][:60]}")

    return inserted_ids


def get_search_queries(themes: list[str] | None = None) -> dict[str, list[str]]:
    """Get search queries for specified themes.

    Args:
        themes: List of theme categories. None = all themes.

    Returns:
        Dict mapping theme -> list of queries.
    """
    if themes is None:
        return dict(NEWS_SEARCH_QUERIES)
    return {t: NEWS_SEARCH_QUERIES[t] for t in themes if t in NEWS_SEARCH_QUERIES}
