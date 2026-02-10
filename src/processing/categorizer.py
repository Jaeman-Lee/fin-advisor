"""Theme categorization for data items."""

import logging
import re

from src.database.operations import DatabaseOperations
from src.utils.config import THEME_CATEGORIES

logger = logging.getLogger(__name__)


def _normalize_text(text: str) -> str:
    """Lowercase and strip non-alphanumeric chars for matching."""
    return re.sub(r"[^a-z0-9\s]", "", text.lower())


def match_keywords(text: str, keywords: str) -> float:
    """Score how well text matches a comma-separated keyword list.

    Returns a score from 0.0 to 1.0 based on fraction of keywords found.
    """
    if not text or not keywords:
        return 0.0

    normalized = _normalize_text(text)
    kw_list = [k.strip().lower() for k in keywords.split(",") if k.strip()]
    if not kw_list:
        return 0.0

    matches = sum(1 for kw in kw_list if kw in normalized)
    return matches / len(kw_list)


def categorize_item(db: DatabaseOperations, title: str,
                    content: str | None = None) -> list[dict]:
    """Categorize a data item into themes based on keyword matching.

    Returns list of matching themes sorted by score, each with:
        {theme_id, category, name, score}
    """
    text = title + " " + (content or "")
    themes = db.get_themes()
    scored: list[dict] = []

    for theme in themes:
        kw = theme.get("keywords", "")
        score = match_keywords(text, kw)
        if score > 0:
            scored.append({
                "theme_id": theme["id"],
                "category": theme["category"],
                "name": theme["name"],
                "score": score,
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def get_best_theme(db: DatabaseOperations, title: str,
                   content: str | None = None) -> dict | None:
    """Get the single best-matching theme for a data item.

    Returns {theme_id, category, name, score} or None.
    """
    matches = categorize_item(db, title, content)
    return matches[0] if matches else None


def categorize_unprocessed(db: DatabaseOperations) -> dict[int, dict]:
    """Categorize all unprocessed items and return mapping.

    Returns dict mapping raw_item_id -> best theme match.
    """
    items = db.get_unprocessed_items(limit=500)
    result: dict[int, dict] = {}

    for item in items:
        best = get_best_theme(db, item["title"], item.get("content"))
        if best:
            result[item["id"]] = best
            logger.debug(f"Item {item['id']} -> {best['category']}/{best['name']} ({best['score']:.2f})")

    logger.info(f"Categorized {len(result)}/{len(items)} items")
    return result
