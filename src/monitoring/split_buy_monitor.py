"""Split-buy tranche trigger evaluation."""

import logging
from datetime import date

from src.database.operations import DatabaseOperations
from src.monitoring.alert_types import Alert, AlertCategory, AlertPriority
from src.monitoring.config import ACTIVE_STRATEGY, SplitBuyStrategy

logger = logging.getLogger(__name__)


def _get_completed_tranches(db: DatabaseOperations, strategy_name: str) -> set[int]:
    """Get set of tranche numbers already executed."""
    trades = db.get_trades(strategy=strategy_name)
    return {t["tranche"] for t in trades if t.get("tranche")}


def _check_tranche2_triggers(db: DatabaseOperations, strategy: SplitBuyStrategy,
                              today: date) -> list[str]:
    """Check 2차 매수 triggers: 5% 하락 OR 2주 경과 OR RSI 45 회복."""
    triggered: list[str] = []

    # Get open positions and current prices
    positions = db.get_open_positions()
    pos_by_ticker = {p["ticker"]: p for p in positions}

    # Trigger 1: Average cost -5% from current price
    total_cost = 0.0
    total_value = 0.0
    for ticker in strategy.tickers:
        pos = pos_by_ticker.get(ticker)
        if not pos:
            continue
        asset_id = db.get_asset_id(ticker)
        if not asset_id:
            continue
        rows = db.get_market_data(asset_id, limit=1)
        if not rows:
            continue
        current = rows[0].get("close", 0)
        total_cost += pos.get("total_cost", 0)
        total_value += current * pos.get("shares", 0)

    if total_cost > 0 and total_value > 0:
        portfolio_return = (total_value / total_cost - 1) * 100
        if portfolio_return <= -5.0:
            triggered.append(f"포트폴리오 {portfolio_return:.1f}% 하락 (≤ -5%)")

    # Trigger 2: Deadline reached
    tranche_cfg = strategy.tranches[1]  # 2차
    if tranche_cfg.deadline and today >= tranche_cfg.deadline:
        triggered.append(f"2주 기한 도래 ({tranche_cfg.deadline})")

    # Trigger 3: RSI 45 recovery (any ticker)
    for ticker in strategy.tickers:
        asset_id = db.get_asset_id(ticker)
        if not asset_id:
            continue
        rows = db.get_market_data(asset_id, limit=1)
        if not rows:
            continue
        rsi = rows[0].get("rsi_14")
        if rsi is not None and rsi >= 45:
            triggered.append(f"{ticker} RSI {rsi:.1f} 회복 (≥ 45)")
            break  # one ticker recovering is enough

    return triggered


def _check_tranche3_triggers(db: DatabaseOperations, strategy: SplitBuyStrategy,
                              today: date) -> list[str]:
    """Check 3차 매수 triggers: MACD 골든크로스 OR 4주 경과 OR SMA20 탈환."""
    triggered: list[str] = []

    # Trigger 1: MACD bullish crossover (any ticker)
    for ticker in strategy.tickers:
        asset_id = db.get_asset_id(ticker)
        if not asset_id:
            continue
        rows = db.get_market_data(asset_id, limit=5)
        if len(rows) < 2:
            continue
        prices = rows[::-1]  # ascending
        from src.analysis.trend_detector import detect_macd_crossover
        events = detect_macd_crossover(prices)
        for evt in events:
            if evt["type"] == "macd_bullish_cross":
                triggered.append(f"{ticker} MACD 골든크로스 ({evt.get('date', '')})")
                break
        if triggered:
            break

    # Trigger 2: Deadline reached
    tranche_cfg = strategy.tranches[2]  # 3차
    if tranche_cfg.deadline and today >= tranche_cfg.deadline:
        triggered.append(f"4주 기한 도래 ({tranche_cfg.deadline})")

    # Trigger 3: Price above SMA20 (any ticker)
    for ticker in strategy.tickers:
        asset_id = db.get_asset_id(ticker)
        if not asset_id:
            continue
        rows = db.get_market_data(asset_id, limit=1)
        if not rows:
            continue
        close = rows[0].get("close")
        sma20 = rows[0].get("sma_20")
        if close and sma20 and close > sma20:
            triggered.append(f"{ticker} SMA20 탈환 (${close:.2f} > ${sma20:.2f})")
            break

    return triggered


def check_split_buy_triggers(db: DatabaseOperations,
                              strategy: SplitBuyStrategy | None = None) -> list[Alert]:
    """Evaluate split-buy tranche triggers and return alerts."""
    strategy = strategy or ACTIVE_STRATEGY
    alerts: list[Alert] = []
    today = date.today()

    completed = _get_completed_tranches(db, strategy.name)
    logger.info(f"Completed tranches: {completed}")

    # Check 2차
    if 2 not in completed and len(strategy.tranches) >= 2:
        reasons = _check_tranche2_triggers(db, strategy, today)
        if reasons:
            tranche = strategy.tranches[1]
            alloc_lines = "\n".join(
                f"  {t}: {q}주" for t, q in tranche.allocations.items()
            )
            alerts.append(Alert(
                category=AlertCategory.SPLIT_BUY_TRIGGER,
                priority=AlertPriority.CRITICAL,
                ticker=None,
                title="2차 분할매수 트리거 충족!",
                message=f"<b>2차 분할매수 트리거 충족!</b>\n\n"
                        f"<b>충족 조건:</b>\n" +
                        "\n".join(f"  - {r}" for r in reasons) +
                        f"\n\n<b>예정 매수:</b> ~${tranche.budget:,.0f}\n"
                        f"{alloc_lines}",
                dedup_key=f"split_buy:{strategy.name}:tranche2",
                permanent_dedup=True,
            ))

    # Check 3차
    if 3 not in completed and len(strategy.tranches) >= 3:
        reasons = _check_tranche3_triggers(db, strategy, today)
        if reasons:
            tranche = strategy.tranches[2]
            alloc_lines = "\n".join(
                f"  {t}: {q}주" for t, q in tranche.allocations.items()
            )
            alerts.append(Alert(
                category=AlertCategory.SPLIT_BUY_TRIGGER,
                priority=AlertPriority.CRITICAL,
                ticker=None,
                title="3차 분할매수 트리거 충족!",
                message=f"<b>3차 분할매수 트리거 충족!</b>\n\n"
                        f"<b>충족 조건:</b>\n" +
                        "\n".join(f"  - {r}" for r in reasons) +
                        f"\n\n<b>예정 매수:</b> ~${tranche.budget:,.0f}\n"
                        f"{alloc_lines}",
                dedup_key=f"split_buy:{strategy.name}:tranche3",
                permanent_dedup=True,
            ))

    # Time triggers (deadline approaching within 2 days)
    for tranche_cfg in strategy.tranches[1:]:  # skip 1차
        if tranche_cfg.tranche in completed:
            continue
        if tranche_cfg.deadline:
            days_until = (tranche_cfg.deadline - today).days
            if 0 < days_until <= 2:
                alerts.append(Alert(
                    category=AlertCategory.TIME_TRIGGER,
                    priority=AlertPriority.CRITICAL,
                    ticker=None,
                    title=f"{tranche_cfg.tranche}차 매수 기한 임박",
                    message=f"<b>{tranche_cfg.tranche}차 분할매수 기한 {days_until}일 남음!</b>\n"
                            f"기한: {tranche_cfg.deadline}\n"
                            f"트리거 미충족 시 시간 트리거로 매수 실행 필요",
                    dedup_key=f"time:{strategy.name}:tranche{tranche_cfg.tranche}:{today.isoformat()}",
                ))

    logger.info(f"Split-buy checks: {len(alerts)} alerts")
    return alerts
