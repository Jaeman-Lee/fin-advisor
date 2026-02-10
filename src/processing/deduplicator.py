"""Deduplication module for raw data items."""

import logging
from difflib import SequenceMatcher

from src.database.operations import DatabaseOperations
from src.utils.config import DEDUP_SIMILARITY_THRESHOLD

logger = logging.getLogger(__name__)


def text_similarity(a: str, b: str) -> float:
    """Compute text similarity ratio between two strings (0.0 to 1.0)."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def find_duplicates(items: list[dict],
                    threshold: float = DEDUP_SIMILARITY_THRESHOLD) -> list[tuple[int, int]]:
    """Find duplicate pairs among items by title+content similarity.

    Args:
        items: List of dicts with 'id', 'title', 'content' keys.
        threshold: Similarity threshold (0.0 to 1.0).

    Returns:
        List of (original_id, duplicate_id) tuples.
    """
    duplicates: list[tuple[int, int]] = []
    seen: list[dict] = []

    for item in items:
        text = (item.get("title", "") + " " + (item.get("content", "") or "")).strip()
        is_dup = False
        for seen_item in seen:
            seen_text = (seen_item.get("title", "") + " " + (seen_item.get("content", "") or "")).strip()
            if text_similarity(text, seen_text) >= threshold:
                duplicates.append((seen_item["id"], item["id"]))
                is_dup = True
                break
        if not is_dup:
            seen.append(item)

    return duplicates


def deduplicate_unprocessed(db: DatabaseOperations,
                            threshold: float = DEDUP_SIMILARITY_THRESHOLD) -> int:
    """Find and mark duplicate unprocessed items.

    Keeps the earliest item (lowest ID) and marks later duplicates as processed
    so they won't be re-processed.

    Returns number of duplicates found.
    """
    items = db.get_unprocessed_items(limit=500)
    if len(items) < 2:
        return 0

    duplicates = find_duplicates(items, threshold)
    for original_id, dup_id in duplicates:
        logger.info(f"Marking item {dup_id} as duplicate of {original_id}")
        db.mark_as_processed(dup_id)

    return len(duplicates)
