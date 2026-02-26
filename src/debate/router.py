"""Routes debate results to appropriate channels based on urgency."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from src.debate.models import DebateResult, Urgency

logger = logging.getLogger(__name__)


def route_debate_results(
    results: list[DebateResult],
    dry_run: bool = False,
) -> dict[str, list[str]]:
    """Route each debate result to the appropriate output channel.

    Returns a summary dict: {"journal": [...], "email": [...], "telegram": [...]}
    """
    routed: dict[str, list[str]] = {"journal": [], "email": [], "telegram": []}

    for result in results:
        # Always log to journal
        routed["journal"].append(result.ticker)

        if result.urgency == Urgency.UNANIMOUS:
            routed["email"].append(result.ticker)
            logger.info(
                "%s: UNANIMOUS %s → journal + email",
                result.ticker, result.final_signal.value,
            )
        elif result.urgency == Urgency.MAJORITY:
            routed["email"].append(result.ticker)
            logger.info(
                "%s: MAJORITY %s → journal + email proposal",
                result.ticker, result.final_signal.value,
            )
        elif result.urgency in (Urgency.SPLIT, Urgency.HIGH_RISK):
            routed["telegram"].append(result.ticker)
            logger.info(
                "%s: %s %s → journal + TELEGRAM decision request",
                result.ticker, result.urgency.value, result.final_signal.value,
            )
            if not dry_run:
                _send_telegram_decision_request(result)

    return routed


def _send_telegram_decision_request(result: DebateResult) -> bool:
    """Send a Telegram message with inline keyboard for user decision."""
    try:
        from src.monitoring.telegram_sender import send_decision_request
        return send_decision_request(result)
    except ImportError:
        logger.warning("telegram_sender not available, skipping Telegram")
        return False
    except Exception as e:
        logger.error("Telegram send failed for %s: %s", result.ticker, e)
        return False


def format_debate_markdown(result: DebateResult) -> str:
    """Format a DebateResult as markdown for journal/email."""
    signal_emoji = {
        "strong_buy": "🟢🟢", "buy": "🟢", "hold": "🟡",
        "sell": "🔴", "strong_sell": "🔴🔴",
    }
    urgency_label = {
        "unanimous": "만장일치", "majority": "다수결",
        "split": "의견 분열", "high_risk": "고위험 거부권",
    }

    lines = [
        f"### {result.ticker} — {signal_emoji.get(result.final_signal.value, '')} "
        f"{result.final_signal.value.upper()} "
        f"(confidence: {result.final_confidence:.0%})",
        f"**결정 유형**: {urgency_label.get(result.urgency.value, result.urgency.value)}",
        "",
        "| Agent | Signal | Confidence | Rationale |",
        "|-------|--------|:----------:|-----------|",
    ]

    for op in result.opinions:
        lines.append(
            f"| {op.agent_name} | {op.signal.value} | {op.confidence:.0%} | "
            f"{op.rationale} |"
        )

    if result.dissenting_views:
        lines.append("")
        lines.append("**반대 의견:**")
        for d in result.dissenting_views:
            lines.append(f"- {d}")

    if result.rebuttals:
        lines.append("")
        lines.append("**교차 검증:**")
        for r in result.rebuttals:
            lines.append(f"- [{r.agent_name} → {r.target_agent}] {r.argument}")

    return "\n".join(lines)


def format_debate_telegram(result: DebateResult) -> str:
    """Format a DebateResult as Telegram HTML message."""
    signal_kr = {
        "strong_buy": "적극 매수", "buy": "매수", "hold": "보유",
        "sell": "매도", "strong_sell": "적극 매도",
    }
    emoji = {"strong_buy": "⬆️⬆️", "buy": "⬆️", "hold": "➡️",
             "sell": "⬇️", "strong_sell": "⬇️⬇️"}

    lines = [
        f"🔔 <b>투자 판단 요청: {result.ticker}</b>",
        "",
        f"최종 의견: {emoji.get(result.final_signal.value, '')} "
        f"<b>{signal_kr.get(result.final_signal.value, result.final_signal.value)}</b> "
        f"({result.final_confidence:.0%})",
        "",
    ]

    # Group by signal direction
    bullish = [op for op in result.opinions if op.signal.value in ("strong_buy", "buy")]
    bearish = [op for op in result.opinions if op.signal.value in ("strong_sell", "sell")]
    neutral = [op for op in result.opinions if op.signal.value == "hold"]

    if bullish:
        lines.append(f"📈 매수 ({len(bullish)}표)")
        for op in bullish:
            lines.append(f"• {op.agent_name}: {op.rationale}")
    if bearish:
        lines.append(f"📉 매도 ({len(bearish)}표)")
        for op in bearish:
            lines.append(f"• {op.agent_name}: {op.rationale}")
    if neutral:
        lines.append(f"⚖️ 중립 ({len(neutral)}표)")
        for op in neutral:
            lines.append(f"• {op.agent_name}: {op.rationale}")

    return "\n".join(lines)


def build_inline_keyboard(result: DebateResult) -> dict:
    """Build Telegram inline keyboard for user decision."""
    debate_id = result.timestamp.replace(":", "").replace("-", "")[:14]
    ticker = result.ticker

    return {
        "inline_keyboard": [
            [
                {"text": "매수 Buy", "callback_data": f"buy:{ticker}:{debate_id}"},
                {"text": "보유 Hold", "callback_data": f"hold:{ticker}:{debate_id}"},
                {"text": "매도 Sell", "callback_data": f"sell:{ticker}:{debate_id}"},
            ],
            [
                {"text": "재분석 요청", "callback_data": f"reanalyze:{ticker}:{debate_id}"},
            ],
        ]
    }
