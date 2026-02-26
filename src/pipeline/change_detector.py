"""Layer 1 core: detect meaningful market changes by comparing current vs previous data."""

from __future__ import annotations

import logging
from datetime import date

from src.database.operations import DatabaseOperations
from src.analysis.trend_detector import detect_macd_crossover
from src.pipeline.event_store import DetectedEvent
from src.utils.config import (
    MONITOR_RSI_OVERSOLD,
    MONITOR_RSI_OVERBOUGHT,
    MONITOR_PRICE_CHANGE_WARN,
    MONITOR_PRICE_CHANGE_CRITICAL,
)

logger = logging.getLogger(__name__)

# ── Thresholds ───────────────────────────────────────────────────────────────

DEFAULT_THRESHOLDS = {
    "price_spike_pct": MONITOR_PRICE_CHANGE_WARN,          # 3%
    "price_spike_critical_pct": MONITOR_PRICE_CHANGE_CRITICAL,  # 5%
    "rsi_oversold": MONITOR_RSI_OVERSOLD,                   # 30
    "rsi_overbought": MONITOR_RSI_OVERBOUGHT,               # 70
    "vix_warning": 25,
    "vix_critical": 30,
}


class ChangeDetector:
    """Compares current market data with previous snapshot to detect meaningful changes."""

    def __init__(self, db: DatabaseOperations,
                 thresholds: dict | None = None):
        self.db = db
        self.th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

    def detect_all(self, tickers: list[str]) -> list[DetectedEvent]:
        """Run all detection checks and return events."""
        events: list[DetectedEvent] = []
        events.extend(self._check_price_changes(tickers))
        events.extend(self._check_rsi_transitions(tickers))
        events.extend(self._check_macd_crosses(tickers))
        events.extend(self._check_vix())
        return events

    # ── Price Spike ──────────────────────────────────────────────────────────

    def _check_price_changes(self, tickers: list[str]) -> list[DetectedEvent]:
        """Detect daily price moves >= threshold."""
        events: list[DetectedEvent] = []
        for ticker in tickers:
            asset_id = self.db.get_asset_id(ticker)
            if not asset_id:
                continue
            rows = self.db.get_market_data(asset_id, limit=2)
            if len(rows) < 2:
                continue

            curr_close = rows[0].get("close")
            prev_close = rows[1].get("close")
            if not curr_close or not prev_close or prev_close == 0:
                continue

            change_pct = (curr_close - prev_close) / prev_close * 100
            abs_change = abs(change_pct)

            if abs_change >= self.th["price_spike_critical_pct"]:
                severity = "critical"
            elif abs_change >= self.th["price_spike_pct"]:
                severity = "warning"
            else:
                continue

            direction = "급등" if change_pct > 0 else "급락"
            events.append(DetectedEvent(
                event_type="price_spike",
                ticker=ticker,
                severity=severity,
                payload={
                    "change_pct": round(change_pct, 2),
                    "close": curr_close,
                    "prev_close": prev_close,
                    "date": rows[0].get("date", ""),
                },
                description=f"{ticker} {direction} {abs_change:.1f}% (${prev_close:.2f}→${curr_close:.2f})",
            ))
        return events

    # ── RSI Transition ───────────────────────────────────────────────────────

    def _check_rsi_transitions(self, tickers: list[str]) -> list[DetectedEvent]:
        """Detect RSI entering or leaving oversold/overbought zones.

        Only fires on TRANSITION (e.g. was 31 now 29), not while already in zone.
        Falls back to absolute level if only 1 data point.
        """
        events: list[DetectedEvent] = []
        for ticker in tickers:
            asset_id = self.db.get_asset_id(ticker)
            if not asset_id:
                continue
            rows = self.db.get_market_data(asset_id, limit=2)
            if not rows:
                continue

            curr_rsi = rows[0].get("rsi_14")
            if curr_rsi is None:
                continue

            prev_rsi = rows[1].get("rsi_14") if len(rows) >= 2 else None

            oversold = self.th["rsi_oversold"]
            overbought = self.th["rsi_overbought"]

            # Transition detection (preferred) or absolute level (first run)
            if prev_rsi is not None:
                # Entry into oversold
                if curr_rsi <= oversold and prev_rsi > oversold:
                    events.append(self._rsi_event(
                        ticker, "entry", "oversold", curr_rsi, prev_rsi, rows[0]))
                # Exit from oversold (recovery)
                elif curr_rsi > oversold and prev_rsi <= oversold:
                    events.append(self._rsi_event(
                        ticker, "exit", "oversold", curr_rsi, prev_rsi, rows[0]))
                # Entry into overbought
                elif curr_rsi >= overbought and prev_rsi < overbought:
                    events.append(self._rsi_event(
                        ticker, "entry", "overbought", curr_rsi, prev_rsi, rows[0]))
                # Exit from overbought
                elif curr_rsi < overbought and prev_rsi >= overbought:
                    events.append(self._rsi_event(
                        ticker, "exit", "overbought", curr_rsi, prev_rsi, rows[0]))
            else:
                # Absolute level fallback (first run, no previous data)
                if curr_rsi <= oversold:
                    events.append(self._rsi_event(
                        ticker, "entry", "oversold", curr_rsi, None, rows[0]))
                elif curr_rsi >= overbought:
                    events.append(self._rsi_event(
                        ticker, "entry", "overbought", curr_rsi, None, rows[0]))

        return events

    def _rsi_event(self, ticker: str, transition: str, zone: str,
                   curr_rsi: float, prev_rsi: float | None,
                   row: dict) -> DetectedEvent:
        severity = "warning" if transition == "entry" else "info"
        if zone == "oversold":
            label = f"과매도 {'진입' if transition == 'entry' else '탈출'}"
        else:
            label = f"과매수 {'진입' if transition == 'entry' else '탈출'}"

        return DetectedEvent(
            event_type="rsi_zone",
            ticker=ticker,
            severity=severity,
            payload={
                "transition": transition,
                "zone": zone,
                "rsi": round(curr_rsi, 1),
                "prev_rsi": round(prev_rsi, 1) if prev_rsi is not None else None,
                "close": row.get("close"),
                "date": row.get("date", ""),
            },
            description=f"{ticker} RSI {label} ({curr_rsi:.1f})",
        )

    # ── MACD Cross ───────────────────────────────────────────────────────────

    def _check_macd_crosses(self, tickers: list[str]) -> list[DetectedEvent]:
        """Detect MACD golden/dead cross using existing trend_detector."""
        events: list[DetectedEvent] = []
        for ticker in tickers:
            asset_id = self.db.get_asset_id(ticker)
            if not asset_id:
                continue
            rows = self.db.get_market_data(asset_id, limit=5)
            if len(rows) < 2:
                continue

            # detect_macd_crossover expects ascending order
            ascending = rows[::-1]
            crosses = detect_macd_crossover(ascending)

            for cross in crosses:
                is_bullish = cross["type"] == "macd_bullish_cross"
                direction = "골든크로스" if is_bullish else "데드크로스"
                severity = "info" if is_bullish else "warning"
                events.append(DetectedEvent(
                    event_type="macd_cross",
                    ticker=ticker,
                    severity=severity,
                    payload={
                        "cross_type": cross["type"],
                        "macd": cross.get("macd"),
                        "signal_line": cross.get("signal_line"),
                        "date": cross.get("date", ""),
                    },
                    description=f"{ticker} MACD {direction}",
                ))
        return events

    # ── VIX ──────────────────────────────────────────────────────────────────

    def _check_vix(self) -> list[DetectedEvent]:
        """Detect VIX crossing above warning/critical thresholds."""
        events: list[DetectedEvent] = []
        asset_id = self.db.get_asset_id("^VIX")
        if not asset_id:
            return events

        rows = self.db.get_market_data(asset_id, limit=2)
        if not rows:
            return events

        curr_vix = rows[0].get("close")
        if curr_vix is None:
            return events

        prev_vix = rows[1].get("close") if len(rows) >= 2 else None

        vix_warn = self.th["vix_warning"]
        vix_crit = self.th["vix_critical"]

        # Critical: VIX >= 30 (or crossing above 30)
        if curr_vix >= vix_crit:
            crossed = prev_vix is None or prev_vix < vix_crit
            if crossed:
                events.append(DetectedEvent(
                    event_type="vix_spike",
                    ticker="^VIX",
                    severity="critical",
                    payload={
                        "vix": round(curr_vix, 2),
                        "prev_vix": round(prev_vix, 2) if prev_vix else None,
                        "threshold": vix_crit,
                        "date": rows[0].get("date", ""),
                    },
                    description=f"VIX {curr_vix:.1f} — 극단적 공포 구간 진입",
                ))
        # Warning: VIX >= 25 (crossing above 25)
        elif curr_vix >= vix_warn:
            crossed = prev_vix is None or prev_vix < vix_warn
            if crossed:
                events.append(DetectedEvent(
                    event_type="vix_spike",
                    ticker="^VIX",
                    severity="warning",
                    payload={
                        "vix": round(curr_vix, 2),
                        "prev_vix": round(prev_vix, 2) if prev_vix else None,
                        "threshold": vix_warn,
                        "date": rows[0].get("date", ""),
                    },
                    description=f"VIX {curr_vix:.1f} — 공포 상승",
                ))
        return events
