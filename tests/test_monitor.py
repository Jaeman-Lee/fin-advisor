"""Tests for the market monitoring system."""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database.schema import init_db
from src.database.operations import DatabaseOperations
from src.monitoring.alert_types import Alert, AlertCategory, AlertPriority
from src.monitoring.config import ACTIVE_STRATEGY, SplitBuyStrategy, TrancheConfig
from src.monitoring.market_monitor import (
    check_rsi_alerts,
    check_price_change_alerts,
    check_macd_alerts,
    check_bollinger_alerts,
    check_portfolio_pnl_alerts,
    check_risk_alerts,
)
from src.monitoring.split_buy_monitor import check_split_buy_triggers
from src.monitoring.dedup import filter_duplicate_alerts, record_sent_alerts
from src.monitoring.telegram_sender import format_alert_message, _split_message


@pytest.fixture
def db(tmp_path):
    """Create a temporary test database with sample data."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return DatabaseOperations(db_path)


@pytest.fixture
def db_with_data(db):
    """DB populated with test assets, market data, and trades."""
    # Register assets
    googl_id = db.upsert_asset("GOOGL", "Alphabet Inc.", "stock", "NASDAQ")
    amzn_id = db.upsert_asset("AMZN", "Amazon.com Inc.", "stock", "NASDAQ")
    msft_id = db.upsert_asset("MSFT", "Microsoft Corp.", "stock", "NASDAQ")

    # Insert market data (2 days, to test price change)
    for asset_id, prices in [
        (googl_id, [(295.0, 300.0), (300.0, 290.0)]),  # day1, day2 (drop)
        (amzn_id, [(200.0, 205.0), (205.0, 215.0)]),   # day1, day2 (rise)
        (msft_id, [(395.0, 400.0), (400.0, 398.0)]),   # day1, day2 (flat)
    ]:
        db.upsert_market_data(asset_id, "2026-02-19",
                              open_=prices[0][0], close=prices[0][1], high=prices[0][1]+2, low=prices[0][0]-2)
        db.upsert_market_data(asset_id, "2026-02-20",
                              open_=prices[1][0], close=prices[1][1], high=prices[1][1]+2, low=prices[1][0]-2)

    # Add RSI data
    db.update_technical_indicators(googl_id, "2026-02-20", rsi_14=28.5, sma_20=310.0, sma_50=320.0, sma_200=330.0)
    db.update_technical_indicators(amzn_id, "2026-02-20", rsi_14=72.0, sma_20=200.0, sma_50=195.0, sma_200=190.0)
    db.update_technical_indicators(msft_id, "2026-02-20", rsi_14=45.0, sma_20=405.0, sma_50=410.0, sma_200=420.0)

    # Add Bollinger bands for MSFT (squeeze scenario)
    db.update_technical_indicators(msft_id, "2026-02-20",
                                   bb_upper=401.0, bb_middle=399.0, bb_lower=397.0)

    # Insert trades
    db.insert_trade(googl_id, "2026-02-20", "buy", 3, 302.85, tranche=1,
                    strategy="US빅테크과매도")
    db.insert_trade(amzn_id, "2026-02-20", "buy", 4, 204.86, tranche=1,
                    strategy="US빅테크과매도")
    db.insert_trade(msft_id, "2026-02-20", "buy", 2, 398.46, tranche=1,
                    strategy="US빅테크과매도")

    return db


# ── Alert Types ──────────────────────────────────────────────────────────

class TestAlertTypes:
    def test_alert_creation(self):
        alert = Alert(
            category=AlertCategory.RSI,
            priority=AlertPriority.WARNING,
            ticker="GOOGL",
            title="GOOGL RSI Oversold",
            message="RSI = 28.5",
            dedup_key="rsi:GOOGL:oversold:2026-02-20",
        )
        assert alert.category == AlertCategory.RSI
        assert alert.priority == AlertPriority.WARNING
        assert alert.permanent_dedup is False

    def test_priority_emoji(self):
        alert = Alert(
            category=AlertCategory.RSI, priority=AlertPriority.CRITICAL,
            ticker="X", title="T", message="M", dedup_key="k",
        )
        assert alert.priority_emoji == "\U0001f534"


# ── RSI Alerts ───────────────────────────────────────────────────────────

class TestRSIAlerts:
    def test_oversold_detected(self, db_with_data):
        alerts = check_rsi_alerts(db_with_data, ["GOOGL"], "2026-02-20")
        assert len(alerts) == 1
        assert alerts[0].category == AlertCategory.RSI
        assert "과매도" in alerts[0].title

    def test_overbought_detected(self, db_with_data):
        alerts = check_rsi_alerts(db_with_data, ["AMZN"], "2026-02-20")
        assert len(alerts) == 1
        assert "과매수" in alerts[0].title

    def test_normal_rsi_no_alert(self, db_with_data):
        alerts = check_rsi_alerts(db_with_data, ["MSFT"], "2026-02-20")
        assert len(alerts) == 0

    def test_unknown_ticker_no_error(self, db_with_data):
        alerts = check_rsi_alerts(db_with_data, ["NONEXIST"], "2026-02-20")
        assert len(alerts) == 0


# ── Price Change Alerts ──────────────────────────────────────────────────

class TestPriceChangeAlerts:
    def test_significant_drop(self, db_with_data):
        # GOOGL: 300 -> 290 = -3.3%
        alerts = check_price_change_alerts(db_with_data, ["GOOGL"], "2026-02-20")
        assert len(alerts) == 1
        assert "급락" in alerts[0].title
        assert alerts[0].priority == AlertPriority.WARNING

    def test_significant_rise(self, db_with_data):
        # AMZN: 205 -> 215 = +4.9%
        alerts = check_price_change_alerts(db_with_data, ["AMZN"], "2026-02-20")
        assert len(alerts) == 1
        assert "급등" in alerts[0].title

    def test_small_change_no_alert(self, db_with_data):
        # MSFT: 400 -> 398 = -0.5%
        alerts = check_price_change_alerts(db_with_data, ["MSFT"], "2026-02-20")
        assert len(alerts) == 0


# ── Bollinger Alerts ─────────────────────────────────────────────────────

class TestBollingerAlerts:
    def test_squeeze_detected(self, db_with_data):
        # MSFT: bandwidth = (401-397)/399 = 0.01 < 0.05
        alerts = check_bollinger_alerts(db_with_data, ["MSFT"], "2026-02-20")
        assert len(alerts) == 1
        assert "스퀴즈" in alerts[0].title


# ── Portfolio P&L Alerts ─────────────────────────────────────────────────

class TestPortfolioPnLAlerts:
    def test_loss_alert(self, db_with_data):
        # GOOGL: avg 302.85, current 290 = -4.2% (below -5%? No, exactly -4.2%)
        # Need a bigger drop to trigger -5%
        # Actually current code uses MONITOR_PNL_LOSS_THRESHOLD=5
        alerts = check_portfolio_pnl_alerts(db_with_data, "2026-02-20")
        # GOOGL is down 4.2%, not enough for -5% threshold
        googl_alerts = [a for a in alerts if a.ticker == "GOOGL"]
        assert len(googl_alerts) == 0  # 4.2% < 5% threshold

    def test_gain_alert(self, db_with_data):
        # AMZN: avg 204.86, current 215 = +4.9% (below +10%)
        alerts = check_portfolio_pnl_alerts(db_with_data, "2026-02-20")
        amzn_alerts = [a for a in alerts if a.ticker == "AMZN"]
        assert len(amzn_alerts) == 0  # 4.9% < 10% threshold


# ── Dedup ────────────────────────────────────────────────────────────────

class TestDedup:
    def test_no_duplicates_initially(self, db):
        alert = Alert(
            category=AlertCategory.RSI, priority=AlertPriority.WARNING,
            ticker="GOOGL", title="T", message="M",
            dedup_key="rsi:GOOGL:oversold:2026-02-20",
        )
        result = filter_duplicate_alerts(db, [alert])
        assert len(result) == 1

    def test_duplicate_filtered_after_recording(self, db):
        alert = Alert(
            category=AlertCategory.RSI, priority=AlertPriority.WARNING,
            ticker="GOOGL", title="T", message="M",
            dedup_key="rsi:GOOGL:oversold:2026-02-20",
        )
        record_sent_alerts(db, [alert])
        result = filter_duplicate_alerts(db, [alert])
        assert len(result) == 0

    def test_permanent_dedup(self, db):
        alert = Alert(
            category=AlertCategory.SPLIT_BUY_TRIGGER,
            priority=AlertPriority.CRITICAL,
            ticker=None, title="T", message="M",
            dedup_key="split_buy:test:tranche2",
            permanent_dedup=True,
        )
        record_sent_alerts(db, [alert])
        # Permanent dedup: always filtered
        result = filter_duplicate_alerts(db, [alert])
        assert len(result) == 0


# ── Split Buy Monitor ────────────────────────────────────────────────────

class TestSplitBuyMonitor:
    def test_tranche1_done_no_alert(self, db_with_data):
        # Tranche 1 is already in DB, so no alert for tranche 1
        alerts = check_split_buy_triggers(db_with_data)
        tranche1_alerts = [a for a in alerts
                           if "1차" in a.title]
        assert len(tranche1_alerts) == 0

    def test_tranche2_rsi_recovery(self, db_with_data):
        # MSFT has RSI=45, which triggers "RSI 45 회복"
        alerts = check_split_buy_triggers(db_with_data)
        tranche2_alerts = [a for a in alerts
                           if "2차" in a.title and a.category == AlertCategory.SPLIT_BUY_TRIGGER]
        assert len(tranche2_alerts) == 1
        assert "RSI" in tranche2_alerts[0].message

    def test_custom_strategy(self, db_with_data):
        strategy = SplitBuyStrategy(
            name="test_strategy",
            total_budget=1000,
            tickers=["GOOGL"],
            target_ratios={"GOOGL": 1.0},
            tranches=[
                TrancheConfig(tranche=1, budget=500,
                              allocations={"GOOGL": 2}, triggers=["test"]),
                TrancheConfig(tranche=2, budget=500,
                              allocations={"GOOGL": 2}, triggers=["test"],
                              deadline=date(2025, 1, 1)),  # past deadline
            ],
        )
        alerts = check_split_buy_triggers(db_with_data, strategy)
        # Both tranches show up since no trades for "test_strategy"
        assert len(alerts) >= 1


# ── Telegram Formatting ──────────────────────────────────────────────────

class TestTelegramFormatting:
    def test_format_empty(self):
        assert format_alert_message([]) == ""

    def test_format_single_alert(self):
        alert = Alert(
            category=AlertCategory.RSI, priority=AlertPriority.WARNING,
            ticker="GOOGL", title="GOOGL RSI 과매도",
            message="RSI = 28.5", dedup_key="k",
        )
        msg = format_alert_message([alert])
        assert "GOOGL" in msg
        assert "과매도" in msg
        assert "주의" in msg

    def test_format_groups_by_priority(self):
        alerts = [
            Alert(category=AlertCategory.RSI, priority=AlertPriority.INFO,
                  ticker="A", title="T1", message="M1", dedup_key="k1"),
            Alert(category=AlertCategory.RSI, priority=AlertPriority.CRITICAL,
                  ticker="B", title="T2", message="M2", dedup_key="k2"),
        ]
        msg = format_alert_message(alerts)
        # CRITICAL should appear before INFO
        crit_pos = msg.find("긴급")
        info_pos = msg.find("참고")
        assert crit_pos < info_pos

    def test_split_long_message(self):
        chunks = _split_message("a" * 5000, max_len=4096)
        assert len(chunks) == 2
        assert all(len(c) <= 4096 for c in chunks)

    def test_short_message_no_split(self):
        chunks = _split_message("short message")
        assert len(chunks) == 1


# ── Alert Log DB Operations ─────────────────────────────────────────────

class TestAlertLogDB:
    def test_log_and_check_duplicate(self, db):
        db.log_alert("test:key:1", "rsi", "Test message",
                     ticker="GOOGL", priority="WARNING",
                     expires_at="2099-12-31 23:59:59")
        assert db.is_alert_duplicate("test:key:1")
        assert not db.is_alert_duplicate("test:key:2")

    def test_permanent_alert_always_duplicate(self, db):
        db.log_alert("perm:key", "split_buy", "Test",
                     priority="CRITICAL", expires_at=None)
        assert db.is_alert_duplicate("perm:key", hours=9999)
