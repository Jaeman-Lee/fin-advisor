"""Persist and query events from the event_queue table."""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class DetectedEvent:
    """A market event detected by the change detector."""

    event_type: str       # 'price_spike', 'rsi_zone', 'macd_cross', 'vix_spike', 'split_buy_trigger'
    ticker: str | None    # None for market-wide events
    severity: str         # 'info', 'warning', 'critical'
    payload: dict         # event-specific data
    description: str      # human-readable summary


class EventStore:
    """Persists detected events and tracks their processing status."""

    def __init__(self, db):
        self.db = db

    def enqueue(self, event: DetectedEvent) -> int:
        """Insert event into event_queue. Returns row ID."""
        return self.db.enqueue_event(
            event_type=event.event_type,
            ticker=event.ticker,
            severity=event.severity,
            payload=json.dumps(event.payload, ensure_ascii=False),
            description=event.description,
        )

    def get_pending(self, limit: int = 50) -> list[dict]:
        """Get unprocessed events ordered by detected_at."""
        rows = self.db.get_pending_events(limit=limit)
        for row in rows:
            if row.get("payload"):
                row["payload"] = json.loads(row["payload"])
        return rows

    def mark_processed(self, event_id: int, result: dict) -> None:
        """Mark event as processed with result data."""
        self.db.mark_event_processed(
            event_id, json.dumps(result, ensure_ascii=False),
        )

    def mark_skipped(self, event_id: int, reason: str) -> None:
        """Mark event as skipped."""
        self.db.mark_event_skipped(event_id, reason)

    def is_recent_duplicate(self, event_type: str, ticker: str | None,
                            hours: int = 6) -> bool:
        """Check if a similar event was already detected within N hours."""
        return self.db.is_event_duplicate(event_type, ticker, hours)
