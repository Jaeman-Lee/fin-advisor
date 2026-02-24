"""Telegram message formatting and sending via Bot API."""

import logging
import os

import requests

from src.monitoring.alert_types import Alert, AlertPriority

logger = logging.getLogger(__name__)

TELEGRAM_MAX_MESSAGE_LENGTH = 4096


def _get_credentials() -> tuple[str, str]:
    """Get Telegram bot token and chat ID from environment."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    return token, chat_id


def format_alert_message(alerts: list[Alert]) -> str:
    """Format alerts into a single Telegram HTML message.

    Groups alerts by priority (CRITICAL > WARNING > INFO).
    """
    if not alerts:
        return ""

    # Group by priority
    by_priority: dict[AlertPriority, list[Alert]] = {}
    for alert in alerts:
        by_priority.setdefault(alert.priority, []).append(alert)

    lines: list[str] = []
    lines.append("<b>📊 시장 모니터링 알림</b>")
    lines.append("")

    for priority in [AlertPriority.CRITICAL, AlertPriority.WARNING, AlertPriority.INFO]:
        group = by_priority.get(priority, [])
        if not group:
            continue

        label = {
            AlertPriority.CRITICAL: "🔴 긴급",
            AlertPriority.WARNING: "🟠 주의",
            AlertPriority.INFO: "🔵 참고",
        }[priority]

        lines.append(f"<b>{'─' * 20}</b>")
        lines.append(f"<b>{label} ({len(group)}건)</b>")
        lines.append("")

        for alert in group:
            lines.append(f"{alert.priority_emoji} <b>{alert.title}</b>")
            lines.append(alert.message)
            lines.append("")

    lines.append(f"<i>총 {len(alerts)}건의 알림</i>")
    return "\n".join(lines)


def _split_message(text: str, max_len: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> list[str]:
    """Split a long message into chunks that fit Telegram's limit."""
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Find a good split point (newline near the limit)
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")

    return chunks


def send_telegram(alerts: list[Alert], dry_run: bool = False) -> bool:
    """Send alerts to Telegram.

    Returns True if all messages sent successfully (or dry_run).
    """
    if not alerts:
        logger.info("No alerts to send")
        return True

    message = format_alert_message(alerts)
    chunks = _split_message(message)

    if dry_run:
        logger.info(f"[DRY RUN] Would send {len(chunks)} message(s) to Telegram:")
        for i, chunk in enumerate(chunks, 1):
            logger.info(f"--- Message {i}/{len(chunks)} ({len(chunk)} chars) ---")
            print(chunk)
            print()
        return True

    token, chat_id = _get_credentials()
    if not token or not chat_id:
        logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    success = True

    for i, chunk in enumerate(chunks, 1):
        try:
            resp = requests.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info(f"Telegram message {i}/{len(chunks)} sent OK")
            else:
                logger.error(f"Telegram API error: {resp.status_code} {resp.text}")
                success = False
        except requests.RequestException as e:
            logger.error(f"Telegram send failed: {e}")
            success = False

    return success
