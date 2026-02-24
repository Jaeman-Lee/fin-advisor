"""Alert deduplication using alert_log DB table."""

import logging
from datetime import datetime, timedelta, timezone

from src.database.operations import DatabaseOperations
from src.monitoring.alert_types import Alert

logger = logging.getLogger(__name__)


def filter_duplicate_alerts(db: DatabaseOperations,
                            alerts: list[Alert],
                            dedup_hours: int = 24) -> list[Alert]:
    """Filter out alerts that have already been sent.

    - Normal alerts: dedup within `dedup_hours` window.
    - permanent_dedup alerts: dedup forever (one-time only).
    """
    unique: list[Alert] = []
    for alert in alerts:
        if db.is_alert_duplicate(alert.dedup_key, hours=dedup_hours):
            logger.debug(f"Skipping duplicate alert: {alert.dedup_key}")
            continue
        unique.append(alert)

    skipped = len(alerts) - len(unique)
    if skipped:
        logger.info(f"Dedup: {skipped} duplicate alerts filtered out")
    return unique


def record_sent_alerts(db: DatabaseOperations, alerts: list[Alert]) -> int:
    """Record sent alerts to alert_log for future dedup.

    Returns count of alerts recorded.
    """
    count = 0
    for alert in alerts:
        expires_at = None
        if not alert.permanent_dedup:
            # Normal alerts expire after 24 hours
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        db.log_alert(
            dedup_key=alert.dedup_key,
            category=alert.category.value,
            message=alert.message,
            ticker=alert.ticker,
            priority=alert.priority.value,
            expires_at=expires_at,
        )
        count += 1

    logger.info(f"Recorded {count} alerts to alert_log")
    return count
