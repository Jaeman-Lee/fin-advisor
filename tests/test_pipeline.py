"""Tests for the event-driven pipeline (Layer 1 + Layer 2)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database.schema import init_db
from src.database.operations import DatabaseOperations
from src.pipeline.event_store import DetectedEvent, EventStore
from src.pipeline.change_detector import ChangeDetector, DEFAULT_THRESHOLDS
from src.pipeline.event_triage import EventTriager, TriageDecision


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return DatabaseOperations(db_path)


@pytest.fixture
def store(db):
    return EventStore(db)


@pytest.fixture
def db_with_market_data(db):
    """DB with 2 days of data for price/RSI/MACD change detection."""
    googl_id = db.upsert_asset("GOOGL", "Alphabet Inc.", "stock", "NASDAQ")
    amzn_id = db.upsert_asset("AMZN", "Amazon.com Inc.", "stock", "NASDAQ")
    msft_id = db.upsert_asset("MSFT", "Microsoft Corp.", "stock", "NASDAQ")
    vix_id = db.upsert_asset("^VIX", "CBOE Volatility Index", "index", "CBOE")

    # GOOGL: -3.3% drop (triggers warning)
    db.upsert_market_data(googl_id, "2026-02-24", open_=300.0, close=300.0, high=302.0, low=298.0)
    db.upsert_market_data(googl_id, "2026-02-25", open_=300.0, close=290.0, high=301.0, low=289.0)

    # AMZN: +5.1% spike (triggers critical)
    db.upsert_market_data(amzn_id, "2026-02-24", open_=200.0, close=200.0, high=202.0, low=198.0)
    db.upsert_market_data(amzn_id, "2026-02-25", open_=200.0, close=210.2, high=211.0, low=199.0)

    # MSFT: +0.5% (no trigger)
    db.upsert_market_data(msft_id, "2026-02-24", open_=400.0, close=400.0, high=402.0, low=398.0)
    db.upsert_market_data(msft_id, "2026-02-25", open_=400.0, close=402.0, high=403.0, low=399.0)

    # RSI transitions: GOOGL drops into oversold, AMZN rises into overbought
    db.update_technical_indicators(googl_id, "2026-02-24", rsi_14=32.0)
    db.update_technical_indicators(googl_id, "2026-02-25", rsi_14=28.0)
    db.update_technical_indicators(amzn_id, "2026-02-24", rsi_14=68.0)
    db.update_technical_indicators(amzn_id, "2026-02-25", rsi_14=73.0)
    db.update_technical_indicators(msft_id, "2026-02-24", rsi_14=50.0)
    db.update_technical_indicators(msft_id, "2026-02-25", rsi_14=51.0)

    # VIX: below threshold (no trigger)
    db.upsert_market_data(vix_id, "2026-02-24", open_=18.0, close=18.5, high=19.0, low=17.0)
    db.upsert_market_data(vix_id, "2026-02-25", open_=18.5, close=19.0, high=20.0, low=18.0)

    return db


@pytest.fixture
def db_vix_spike(db):
    """DB where VIX crosses above 25."""
    vix_id = db.upsert_asset("^VIX", "CBOE Volatility Index", "index", "CBOE")
    db.upsert_market_data(vix_id, "2026-02-24", open_=22.0, close=23.0, high=24.0, low=21.0)
    db.upsert_market_data(vix_id, "2026-02-25", open_=24.0, close=27.0, high=28.0, low=23.0)
    return db


@pytest.fixture
def db_vix_critical(db):
    """DB where VIX crosses above 30."""
    vix_id = db.upsert_asset("^VIX", "CBOE Volatility Index", "index", "CBOE")
    db.upsert_market_data(vix_id, "2026-02-24", open_=28.0, close=29.0, high=30.0, low=27.0)
    db.upsert_market_data(vix_id, "2026-02-25", open_=29.0, close=32.0, high=33.0, low=28.0)
    return db


# ── EventStore Tests ─────────────────────────────────────────────────────────

class TestEventStore:
    def test_enqueue_and_get_pending(self, store, db):
        event = DetectedEvent(
            event_type="price_spike", ticker="GOOGL", severity="warning",
            payload={"change_pct": -3.3}, description="GOOGL 급락 3.3%",
        )
        event_id = store.enqueue(event)
        assert event_id > 0

        pending = store.get_pending()
        assert len(pending) == 1
        assert pending[0]["event_type"] == "price_spike"
        assert pending[0]["ticker"] == "GOOGL"
        assert pending[0]["payload"]["change_pct"] == -3.3

    def test_mark_processed(self, store, db):
        event = DetectedEvent(
            event_type="rsi_zone", ticker="AMZN", severity="warning",
            payload={"rsi": 73.0}, description="test",
        )
        event_id = store.enqueue(event)
        store.mark_processed(event_id, {"action": "debate", "signal": "hold"})

        pending = store.get_pending()
        assert len(pending) == 0

    def test_mark_skipped(self, store, db):
        event = DetectedEvent(
            event_type="macd_cross", ticker="MSFT", severity="info",
            payload={}, description="test",
        )
        event_id = store.enqueue(event)
        store.mark_skipped(event_id, "duplicate")

        pending = store.get_pending()
        assert len(pending) == 0

    def test_dedup_within_window(self, store, db):
        event = DetectedEvent(
            event_type="price_spike", ticker="GOOGL", severity="warning",
            payload={}, description="test",
        )
        store.enqueue(event)
        assert store.is_recent_duplicate("price_spike", "GOOGL", hours=6) is True

    def test_dedup_different_ticker(self, store, db):
        event = DetectedEvent(
            event_type="price_spike", ticker="GOOGL", severity="warning",
            payload={}, description="test",
        )
        store.enqueue(event)
        assert store.is_recent_duplicate("price_spike", "AMZN", hours=6) is False

    def test_dedup_market_wide(self, store, db):
        event = DetectedEvent(
            event_type="vix_spike", ticker=None, severity="critical",
            payload={}, description="test",
        )
        store.enqueue(event)
        assert store.is_recent_duplicate("vix_spike", None, hours=6) is True


# ── ChangeDetector Tests ─────────────────────────────────────────────────────

class TestChangeDetector:
    def test_price_spike_warning(self, db_with_market_data):
        detector = ChangeDetector(db_with_market_data)
        events = detector._check_price_changes(["GOOGL"])
        assert len(events) == 1
        assert events[0].severity == "warning"
        assert events[0].ticker == "GOOGL"
        assert "급락" in events[0].description

    def test_price_spike_critical(self, db_with_market_data):
        detector = ChangeDetector(db_with_market_data)
        events = detector._check_price_changes(["AMZN"])
        assert len(events) == 1
        assert events[0].severity == "critical"
        assert "급등" in events[0].description

    def test_no_price_spike_small_change(self, db_with_market_data):
        detector = ChangeDetector(db_with_market_data)
        events = detector._check_price_changes(["MSFT"])
        assert len(events) == 0

    def test_rsi_oversold_entry(self, db_with_market_data):
        detector = ChangeDetector(db_with_market_data)
        events = detector._check_rsi_transitions(["GOOGL"])
        assert len(events) == 1
        assert events[0].event_type == "rsi_zone"
        assert events[0].payload["zone"] == "oversold"
        assert events[0].payload["transition"] == "entry"

    def test_rsi_overbought_entry(self, db_with_market_data):
        detector = ChangeDetector(db_with_market_data)
        events = detector._check_rsi_transitions(["AMZN"])
        assert len(events) == 1
        assert events[0].payload["zone"] == "overbought"
        assert events[0].payload["transition"] == "entry"

    def test_rsi_no_transition(self, db_with_market_data):
        """RSI stays in normal range — no event."""
        detector = ChangeDetector(db_with_market_data)
        events = detector._check_rsi_transitions(["MSFT"])
        assert len(events) == 0

    def test_vix_no_spike(self, db_with_market_data):
        detector = ChangeDetector(db_with_market_data)
        events = detector._check_vix()
        assert len(events) == 0

    def test_vix_warning_spike(self, db_vix_spike):
        detector = ChangeDetector(db_vix_spike)
        events = detector._check_vix()
        assert len(events) == 1
        assert events[0].severity == "warning"
        assert events[0].event_type == "vix_spike"

    def test_vix_critical_spike(self, db_vix_critical):
        detector = ChangeDetector(db_vix_critical)
        events = detector._check_vix()
        assert len(events) == 1
        assert events[0].severity == "critical"

    def test_detect_all_multiple_events(self, db_with_market_data):
        detector = ChangeDetector(db_with_market_data)
        events = detector.detect_all(["GOOGL", "AMZN", "MSFT"])
        # GOOGL: price_spike + rsi_zone, AMZN: price_spike + rsi_zone, MSFT: nothing
        assert len(events) >= 4

    def test_detect_all_calm_market(self, db_with_market_data):
        """MSFT only — no significant changes."""
        detector = ChangeDetector(db_with_market_data)
        events = detector.detect_all(["MSFT"])
        assert len(events) == 0

    def test_custom_thresholds(self, db_with_market_data):
        """Custom threshold makes MSFT's 0.5% change trigger."""
        detector = ChangeDetector(
            db_with_market_data,
            thresholds={"price_spike_pct": 0.1, "price_spike_critical_pct": 0.3},
        )
        events = detector._check_price_changes(["MSFT"])
        assert len(events) == 1


# ── EventTriager Tests ───────────────────────────────────────────────────────

class TestEventTriager:
    def _make_event(self, event_type="price_spike", ticker="GOOGL",
                    severity="critical"):
        return DetectedEvent(
            event_type=event_type, ticker=ticker, severity=severity,
            payload={}, description="test event",
        )

    def test_critical_held_triggers_debate(self):
        triager = EventTriager(held_tickers={"GOOGL"})
        decisions = triager.triage([self._make_event(severity="critical")])
        assert decisions[0].action == "debate"

    def test_critical_non_held_triggers_alert(self):
        triager = EventTriager(held_tickers={"AMZN"})
        decisions = triager.triage([self._make_event(ticker="TSLA", severity="critical")])
        assert decisions[0].action == "alert_only"

    def test_warning_held_triggers_alert(self):
        triager = EventTriager(held_tickers={"GOOGL"})
        decisions = triager.triage([self._make_event(severity="warning")])
        assert decisions[0].action == "alert_only"

    def test_rsi_warning_held_triggers_debate(self):
        triager = EventTriager(held_tickers={"GOOGL"})
        event = self._make_event(event_type="rsi_zone", severity="warning")
        decisions = triager.triage([event])
        assert decisions[0].action == "debate"

    def test_rsi_info_recovery_held_triggers_alert(self):
        triager = EventTriager(held_tickers={"GOOGL"})
        event = self._make_event(event_type="rsi_zone", severity="info")
        decisions = triager.triage([event])
        assert decisions[0].action == "alert_only"

    def test_vix_critical_triggers_debate(self):
        triager = EventTriager(held_tickers={"GOOGL"})
        event = self._make_event(event_type="vix_spike", ticker="^VIX", severity="critical")
        decisions = triager.triage([event])
        assert decisions[0].action == "debate"

    def test_vix_warning_triggers_alert(self):
        triager = EventTriager(held_tickers={"GOOGL"})
        event = self._make_event(event_type="vix_spike", ticker="^VIX", severity="warning")
        decisions = triager.triage([event])
        assert decisions[0].action == "alert_only"

    def test_macd_death_cross_held_triggers_debate(self):
        triager = EventTriager(held_tickers={"GOOGL"})
        event = self._make_event(event_type="macd_cross", severity="warning")
        decisions = triager.triage([event])
        assert decisions[0].action == "debate"

    def test_macd_golden_cross_non_held_logs(self):
        triager = EventTriager(held_tickers=set())
        event = self._make_event(event_type="macd_cross", ticker="TSLA", severity="info")
        decisions = triager.triage([event])
        assert decisions[0].action == "log_only"

    def test_unknown_event_defaults_to_log(self):
        triager = EventTriager(held_tickers={"GOOGL"})
        event = self._make_event(event_type="unknown_type", severity="info")
        decisions = triager.triage([event])
        assert decisions[0].action == "log_only"

    def test_multiple_events_mixed(self):
        triager = EventTriager(held_tickers={"GOOGL", "AMZN"})
        events = [
            self._make_event(event_type="price_spike", ticker="GOOGL", severity="critical"),
            self._make_event(event_type="rsi_zone", ticker="AMZN", severity="warning"),
            self._make_event(event_type="macd_cross", ticker="TSLA", severity="info"),
        ]
        decisions = triager.triage(events)
        assert decisions[0].action == "debate"
        assert decisions[1].action == "debate"
        assert decisions[2].action == "log_only"

    def test_empty_events(self):
        triager = EventTriager(held_tickers={"GOOGL"})
        decisions = triager.triage([])
        assert decisions == []


# ── Integration Tests ────────────────────────────────────────────────────────

class TestIntegration:
    def test_full_pipeline_detect_to_enqueue(self, db_with_market_data):
        """Layer 1: detect changes and enqueue events."""
        detector = ChangeDetector(db_with_market_data)
        store = EventStore(db_with_market_data)

        events = detector.detect_all(["GOOGL", "AMZN", "MSFT"])
        assert len(events) >= 4

        for event in events:
            store.enqueue(event)

        pending = store.get_pending()
        assert len(pending) == len(events)

    def test_full_pipeline_detect_triage(self, db_with_market_data):
        """Layer 1 → Layer 2: detect → triage."""
        detector = ChangeDetector(db_with_market_data)
        events = detector.detect_all(["GOOGL", "AMZN"])

        triager = EventTriager(held_tickers={"GOOGL", "AMZN"})
        decisions = triager.triage(events)

        # Should have debate actions for held positions with critical/warning events
        debate_count = sum(1 for d in decisions if d.action == "debate")
        assert debate_count >= 2  # at least GOOGL rsi + AMZN price spike

    def test_dedup_prevents_reprocessing(self, db_with_market_data):
        """Dedup prevents same event from being enqueued twice."""
        store = EventStore(db_with_market_data)
        event = DetectedEvent(
            event_type="price_spike", ticker="GOOGL", severity="warning",
            payload={}, description="test",
        )
        store.enqueue(event)
        assert store.is_recent_duplicate("price_spike", "GOOGL") is True
