"""Market alert checks: RSI, price change, MACD, golden/death cross, Bollinger, risk."""

import logging
from datetime import date

from src.database.operations import DatabaseOperations
from src.analysis.trend_detector import (
    detect_macd_crossover,
    detect_golden_death_cross,
    detect_bollinger_squeeze,
)
from src.analysis.risk_assessor import assess_asset_risk
from src.monitoring.alert_types import Alert, AlertCategory, AlertPriority
from src.utils.config import (
    MONITOR_RSI_OVERSOLD,
    MONITOR_RSI_OVERBOUGHT,
    MONITOR_PRICE_CHANGE_WARN,
    MONITOR_PRICE_CHANGE_CRITICAL,
    MONITOR_BOLLINGER_SQUEEZE_BW,
    MONITOR_RISK_THRESHOLD,
    MONITOR_PNL_LOSS_THRESHOLD,
    MONITOR_PNL_GAIN_THRESHOLD,
)

logger = logging.getLogger(__name__)


def check_rsi_alerts(db: DatabaseOperations, tickers: list[str],
                     today: str) -> list[Alert]:
    """Check RSI extreme levels for given tickers."""
    alerts: list[Alert] = []
    for ticker in tickers:
        asset_id = db.get_asset_id(ticker)
        if not asset_id:
            continue
        rows = db.get_market_data(asset_id, limit=1)
        if not rows:
            continue
        latest = rows[0]
        rsi = latest.get("rsi_14")
        if rsi is None:
            continue

        if rsi <= MONITOR_RSI_OVERSOLD:
            alerts.append(Alert(
                category=AlertCategory.RSI,
                priority=AlertPriority.WARNING,
                ticker=ticker,
                title=f"{ticker} RSI 과매도",
                message=f"<b>{ticker}</b> RSI = <b>{rsi:.1f}</b> (≤ {MONITOR_RSI_OVERSOLD})\n"
                        f"종가: ${latest.get('close', 0):.2f} ({latest.get('date', '')})",
                dedup_key=f"rsi:{ticker}:oversold:{today}",
                data={"rsi": rsi, "close": latest.get("close")},
            ))
        elif rsi >= MONITOR_RSI_OVERBOUGHT:
            alerts.append(Alert(
                category=AlertCategory.RSI,
                priority=AlertPriority.WARNING,
                ticker=ticker,
                title=f"{ticker} RSI 과매수",
                message=f"<b>{ticker}</b> RSI = <b>{rsi:.1f}</b> (≥ {MONITOR_RSI_OVERBOUGHT})\n"
                        f"종가: ${latest.get('close', 0):.2f} ({latest.get('date', '')})",
                dedup_key=f"rsi:{ticker}:overbought:{today}",
                data={"rsi": rsi, "close": latest.get("close")},
            ))
    return alerts


def check_price_change_alerts(db: DatabaseOperations, tickers: list[str],
                              today: str) -> list[Alert]:
    """Check for significant daily price changes."""
    alerts: list[Alert] = []
    for ticker in tickers:
        asset_id = db.get_asset_id(ticker)
        if not asset_id:
            continue
        rows = db.get_market_data(asset_id, limit=2)
        if len(rows) < 2:
            continue
        # rows are DESC, so [0] is latest, [1] is previous
        curr_close = rows[0].get("close")
        prev_close = rows[1].get("close")
        if not curr_close or not prev_close or prev_close == 0:
            continue

        change_pct = (curr_close - prev_close) / prev_close * 100
        abs_change = abs(change_pct)

        if abs_change >= MONITOR_PRICE_CHANGE_CRITICAL:
            priority = AlertPriority.CRITICAL
        elif abs_change >= MONITOR_PRICE_CHANGE_WARN:
            priority = AlertPriority.WARNING
        else:
            continue

        direction = "급등" if change_pct > 0 else "급락"
        alerts.append(Alert(
            category=AlertCategory.PRICE_CHANGE,
            priority=priority,
            ticker=ticker,
            title=f"{ticker} {direction} {abs_change:.1f}%",
            message=f"<b>{ticker}</b> {direction} <b>{change_pct:+.1f}%</b>\n"
                    f"${prev_close:.2f} → ${curr_close:.2f} ({rows[0].get('date', '')})",
            dedup_key=f"price:{ticker}:{direction}:{today}",
            data={"change_pct": change_pct, "close": curr_close, "prev_close": prev_close},
        ))
    return alerts


def check_macd_alerts(db: DatabaseOperations, tickers: list[str],
                      today: str) -> list[Alert]:
    """Check for MACD crossovers."""
    alerts: list[Alert] = []
    for ticker in tickers:
        asset_id = db.get_asset_id(ticker)
        if not asset_id:
            continue
        rows = db.get_market_data(asset_id, limit=5)
        if len(rows) < 2:
            continue
        # ascending for crossover detection
        prices = rows[::-1]
        events = detect_macd_crossover(prices)
        for evt in events:
            is_bullish = evt["type"] == "macd_bullish_cross"
            priority = AlertPriority.INFO if is_bullish else AlertPriority.WARNING
            direction = "강세" if is_bullish else "약세"
            alerts.append(Alert(
                category=AlertCategory.MACD,
                priority=priority,
                ticker=ticker,
                title=f"{ticker} MACD {direction} 크로스",
                message=f"<b>{ticker}</b> MACD {direction} 크로스오버\n"
                        f"MACD: {evt.get('macd', 0):.4f}, Signal: {evt.get('signal_line', 0):.4f}\n"
                        f"날짜: {evt.get('date', '')}",
                dedup_key=f"macd:{ticker}:{evt['type']}:{today}",
                data=evt,
            ))
    return alerts


def check_cross_alerts(db: DatabaseOperations, tickers: list[str],
                       today: str) -> list[Alert]:
    """Check for golden/death cross (SMA50 vs SMA200)."""
    alerts: list[Alert] = []
    for ticker in tickers:
        asset_id = db.get_asset_id(ticker)
        if not asset_id:
            continue
        rows = db.get_market_data(asset_id, limit=5)
        if len(rows) < 2:
            continue
        prices = rows[::-1]  # ascending
        events = detect_golden_death_cross(prices)
        for evt in events:
            is_golden = evt["type"] == "golden_cross"
            priority = AlertPriority.INFO if is_golden else AlertPriority.WARNING
            name = "골든크로스" if is_golden else "데드크로스"
            alerts.append(Alert(
                category=AlertCategory.GOLDEN_DEATH_CROSS,
                priority=priority,
                ticker=ticker,
                title=f"{ticker} {name}",
                message=f"<b>{ticker}</b> {name}\n"
                        f"SMA50: {evt.get('sma_50', 0):.2f}, SMA200: {evt.get('sma_200', 0):.2f}\n"
                        f"날짜: {evt.get('date', '')}",
                dedup_key=f"cross:{ticker}:{evt['type']}:{today}",
                data=evt,
            ))
    return alerts


def check_bollinger_alerts(db: DatabaseOperations, tickers: list[str],
                           today: str) -> list[Alert]:
    """Check for Bollinger Band squeezes."""
    alerts: list[Alert] = []
    for ticker in tickers:
        asset_id = db.get_asset_id(ticker)
        if not asset_id:
            continue
        rows = db.get_market_data(asset_id, limit=1)
        if not rows:
            continue
        latest = rows[0]
        upper = latest.get("bb_upper")
        lower = latest.get("bb_lower")
        middle = latest.get("bb_middle")
        if not all([upper, lower, middle]) or middle == 0:
            continue

        bandwidth = (upper - lower) / middle
        if bandwidth < MONITOR_BOLLINGER_SQUEEZE_BW:
            alerts.append(Alert(
                category=AlertCategory.BOLLINGER_SQUEEZE,
                priority=AlertPriority.INFO,
                ticker=ticker,
                title=f"{ticker} 볼린저 스퀴즈",
                message=f"<b>{ticker}</b> 볼린저밴드 스퀴즈 (밴드폭={bandwidth:.4f})\n"
                        f"상단: ${upper:.2f}, 하단: ${lower:.2f}\n"
                        f"종가: ${latest.get('close', 0):.2f} ({latest.get('date', '')})",
                dedup_key=f"boll:{ticker}:squeeze:{today}",
                data={"bandwidth": bandwidth},
            ))
    return alerts


def check_portfolio_pnl_alerts(db: DatabaseOperations, today: str) -> list[Alert]:
    """Check portfolio P&L against thresholds.

    Requires current market prices in DB.
    """
    alerts: list[Alert] = []
    positions = db.get_open_positions()
    for pos in positions:
        ticker = pos["ticker"]
        avg_price = pos.get("avg_price")
        shares = pos.get("shares", 0)
        if not avg_price or shares <= 0:
            continue

        asset_id = db.get_asset_id(ticker)
        if not asset_id:
            continue
        rows = db.get_market_data(asset_id, limit=1)
        if not rows:
            continue
        current_price = rows[0].get("close")
        if not current_price:
            continue

        pnl_pct = (current_price / avg_price - 1) * 100
        pnl_usd = (current_price - avg_price) * shares

        if pnl_pct <= -MONITOR_PNL_LOSS_THRESHOLD:
            alerts.append(Alert(
                category=AlertCategory.PORTFOLIO_PNL,
                priority=AlertPriority.CRITICAL,
                ticker=ticker,
                title=f"{ticker} 손실 {pnl_pct:.1f}%",
                message=f"<b>{ticker}</b> 포지션 손실 <b>{pnl_pct:.1f}%</b> (${pnl_usd:+,.0f})\n"
                        f"평균가: ${avg_price:.2f} → 현재: ${current_price:.2f}\n"
                        f"보유: {shares}주",
                dedup_key=f"pnl:{ticker}:loss:{today}",
                data={"pnl_pct": pnl_pct, "pnl_usd": pnl_usd},
            ))
        elif pnl_pct >= MONITOR_PNL_GAIN_THRESHOLD:
            alerts.append(Alert(
                category=AlertCategory.PORTFOLIO_PNL,
                priority=AlertPriority.INFO,
                ticker=ticker,
                title=f"{ticker} 수익 +{pnl_pct:.1f}%",
                message=f"<b>{ticker}</b> 포지션 수익 <b>+{pnl_pct:.1f}%</b> (${pnl_usd:+,.0f})\n"
                        f"평균가: ${avg_price:.2f} → 현재: ${current_price:.2f}\n"
                        f"보유: {shares}주",
                dedup_key=f"pnl:{ticker}:gain:{today}",
                data={"pnl_pct": pnl_pct, "pnl_usd": pnl_usd},
            ))
    return alerts


def check_risk_alerts(db: DatabaseOperations, tickers: list[str],
                      today: str) -> list[Alert]:
    """Check if any asset's risk score exceeds threshold."""
    alerts: list[Alert] = []
    for ticker in tickers:
        asset_id = db.get_asset_id(ticker)
        if not asset_id:
            continue
        risk = assess_asset_risk(db, asset_id)
        score = risk.get("risk_score")
        if score is not None and score >= MONITOR_RISK_THRESHOLD:
            alerts.append(Alert(
                category=AlertCategory.RISK,
                priority=AlertPriority.WARNING,
                ticker=ticker,
                title=f"{ticker} 리스크 상승",
                message=f"<b>{ticker}</b> 리스크 점수 <b>{score:.2f}</b> ({risk.get('risk_level', '')})\n"
                        f"변동성: {risk.get('volatility_annualized', 'N/A')}\n"
                        f"최대낙폭: {risk.get('max_drawdown', 'N/A')}\n"
                        f"RSI: {risk.get('current_rsi', 'N/A')}",
                dedup_key=f"risk:{ticker}:high:{today}",
                data=risk,
            ))
    return alerts


def run_all_market_checks(db: DatabaseOperations,
                          tickers: list[str]) -> list[Alert]:
    """Run all market-related alert checks and return combined alerts."""
    today = date.today().isoformat()
    alerts: list[Alert] = []

    logger.info("Checking RSI alerts...")
    alerts.extend(check_rsi_alerts(db, tickers, today))

    logger.info("Checking price change alerts...")
    alerts.extend(check_price_change_alerts(db, tickers, today))

    logger.info("Checking MACD crossover alerts...")
    alerts.extend(check_macd_alerts(db, tickers, today))

    logger.info("Checking golden/death cross alerts...")
    alerts.extend(check_cross_alerts(db, tickers, today))

    logger.info("Checking Bollinger squeeze alerts...")
    alerts.extend(check_bollinger_alerts(db, tickers, today))

    logger.info("Checking portfolio P&L alerts...")
    alerts.extend(check_portfolio_pnl_alerts(db, today))

    logger.info("Checking risk alerts...")
    alerts.extend(check_risk_alerts(db, tickers, today))

    logger.info(f"Market checks complete: {len(alerts)} alerts generated")
    return alerts
