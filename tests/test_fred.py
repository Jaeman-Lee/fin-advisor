"""Tests for FRED macro data collection and storage."""

import json
from unittest.mock import patch, MagicMock

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database.schema import init_db
from src.database.operations import DatabaseOperations
from src.collection.fred_data import (
    fetch_fred_series,
    collect_fred_series,
    collect_all_fred,
    get_macro_dashboard,
    get_yield_spread,
    get_inflation_trend,
)
from src.utils.config import FRED_SERIES


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path):
    """Create an isolated test database."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return DatabaseOperations(db_path)


MOCK_FRED_RESPONSE = {
    "observations": [
        {"date": "2026-02-20", "value": "4.33"},
        {"date": "2026-02-21", "value": "4.35"},
        {"date": "2026-02-24", "value": "."},  # missing value
    ]
}


# ── Config Tests ──────────────────────────────────────────────────────────

class TestFredConfig:
    def test_series_defined(self):
        assert len(FRED_SERIES) > 0

    def test_series_structure(self):
        for sid, meta in FRED_SERIES.items():
            assert len(meta) == 3, f"{sid} should have (name, category, frequency)"
            name, category, frequency = meta
            assert isinstance(name, str) and name
            assert isinstance(category, str) and category
            assert frequency in ("daily", "weekly", "monthly", "quarterly")

    def test_key_series_present(self):
        essential = ["DFF", "DGS10", "UNRATE", "CPIAUCSL", "GDP"]
        for sid in essential:
            assert sid in FRED_SERIES, f"Essential series {sid} missing"


# ── Fetch Tests ───────────────────────────────────────────────────────────

class TestFetchFredSeries:
    def test_missing_api_key(self):
        with patch("src.collection.fred_data.FRED_API_KEY", ""):
            with pytest.raises(ValueError, match="FRED API key required"):
                fetch_fred_series("DFF")

    @patch("src.collection.fred_data.requests.get")
    def test_fetch_parses_observations(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_FRED_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_fred_series("DGS10", api_key="test_key")
        assert len(result) == 3
        assert result[0] == {"date": "2026-02-20", "value": 4.33}
        assert result[1] == {"date": "2026-02-21", "value": 4.35}
        assert result[2] == {"date": "2026-02-24", "value": None}  # "." → None

    @patch("src.collection.fred_data.requests.get")
    def test_fetch_passes_date_params(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"observations": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        fetch_fred_series("DFF", api_key="key", start_date="2025-01-01", end_date="2026-01-01")

        call_params = mock_get.call_args[1]["params"]
        assert call_params["observation_start"] == "2025-01-01"
        assert call_params["observation_end"] == "2026-01-01"

    @patch("src.collection.fred_data.requests.get")
    def test_fetch_empty_response(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"observations": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_fred_series("FAKE", api_key="key")
        assert result == []


# ── DB CRUD Tests ─────────────────────────────────────────────────────────

class TestMacroIndicatorCRUD:
    def test_upsert_and_get(self, db):
        db.upsert_macro_indicator("DFF", "2026-02-20", 4.33)
        db.upsert_macro_indicator("DFF", "2026-02-21", 4.35)

        rows = db.get_macro_series("DFF")
        assert len(rows) == 2
        assert rows[0]["date"] == "2026-02-21"  # DESC order
        assert rows[0]["value"] == 4.35

    def test_upsert_updates_existing(self, db):
        db.upsert_macro_indicator("DFF", "2026-02-20", 4.33)
        db.upsert_macro_indicator("DFF", "2026-02-20", 4.50)  # update

        rows = db.get_macro_series("DFF")
        assert len(rows) == 1
        assert rows[0]["value"] == 4.50

    def test_null_value(self, db):
        db.upsert_macro_indicator("DFF", "2026-02-20", None)
        rows = db.get_macro_series("DFF")
        assert len(rows) == 1
        assert rows[0]["value"] is None

    def test_date_range_filter(self, db):
        db.upsert_macro_indicator("DFF", "2026-01-01", 4.0)
        db.upsert_macro_indicator("DFF", "2026-02-01", 4.2)
        db.upsert_macro_indicator("DFF", "2026-03-01", 4.4)

        rows = db.get_macro_series("DFF", start_date="2026-02-01", end_date="2026-02-28")
        assert len(rows) == 1
        assert rows[0]["date"] == "2026-02-01"

    def test_get_latest_value(self, db):
        db.upsert_macro_indicator("UNRATE", "2026-01-01", 4.1)
        db.upsert_macro_indicator("UNRATE", "2026-02-01", 4.0)
        db.upsert_macro_indicator("UNRATE", "2026-03-01", None)  # missing

        latest = db.get_latest_macro_value("UNRATE")
        assert latest["value"] == 4.0  # skips None
        assert latest["date"] == "2026-02-01"

    def test_get_latest_value_nonexistent(self, db):
        assert db.get_latest_macro_value("FAKE") is None

    def test_get_macro_snapshot(self, db):
        db.upsert_macro_indicator("DFF", "2026-02-20", 4.33)
        db.upsert_macro_indicator("DFF", "2026-02-21", 4.35)
        db.upsert_macro_indicator("UNRATE", "2026-01-01", 4.1)

        snapshot = db.get_macro_snapshot()
        assert len(snapshot) == 2
        by_series = {r["series_id"]: r for r in snapshot}
        assert by_series["DFF"]["value"] == 4.35
        assert by_series["UNRATE"]["value"] == 4.1

    def test_get_macro_snapshot_filtered(self, db):
        db.upsert_macro_indicator("DFF", "2026-02-20", 4.33)
        db.upsert_macro_indicator("UNRATE", "2026-01-01", 4.1)

        snapshot = db.get_macro_snapshot(series_ids=["DFF"])
        assert len(snapshot) == 1
        assert snapshot[0]["series_id"] == "DFF"

    def test_limit(self, db):
        for i in range(10):
            db.upsert_macro_indicator("DFF", f"2026-01-{i+1:02d}", 4.0 + i * 0.01)

        rows = db.get_macro_series("DFF", limit=3)
        assert len(rows) == 3


# ── Collection Integration Tests ─────────────────────────────────────────

class TestCollectFredSeries:
    @patch("src.collection.fred_data.fetch_fred_series")
    def test_collect_single(self, mock_fetch, db):
        mock_fetch.return_value = [
            {"date": "2026-02-20", "value": 4.33},
            {"date": "2026-02-21", "value": 4.35},
        ]

        count = collect_fred_series(db, "DFF", api_key="test")
        assert count == 2

        rows = db.get_macro_series("DFF")
        assert len(rows) == 2

    @patch("src.collection.fred_data.fetch_fred_series")
    def test_collect_handles_error(self, mock_fetch, db):
        import requests
        mock_fetch.side_effect = requests.RequestException("timeout")

        count = collect_fred_series(db, "DFF", api_key="test")
        assert count == 0

    @patch("src.collection.fred_data.collect_fred_series")
    def test_collect_all(self, mock_collect, db):
        mock_collect.return_value = 100

        results = collect_all_fred(db, series_ids=["DFF", "UNRATE"], api_key="test")
        assert len(results) == 2
        assert results["DFF"] == 100
        assert results["UNRATE"] == 100

    @patch("src.collection.fred_data.collect_fred_series")
    def test_collect_by_category(self, mock_collect, db):
        mock_collect.return_value = 50

        results = collect_all_fred(db, category="inflation", api_key="test")
        expected_count = sum(1 for _, (_, cat, _) in FRED_SERIES.items() if cat == "inflation")
        assert len(results) == expected_count


# ── Dashboard / Analysis Tests ────────────────────────────────────────────

class TestMacroDashboard:
    def test_empty_dashboard(self, db):
        dashboard = get_macro_dashboard(db)
        for category, items in dashboard.items():
            for item in items:
                assert item["value"] is None

    def test_dashboard_with_data(self, db):
        db.upsert_macro_indicator("DFF", "2026-02-20", 4.33)
        db.upsert_macro_indicator("UNRATE", "2026-01-01", 4.1)

        dashboard = get_macro_dashboard(db)
        assert "interest_rate" in dashboard
        assert "employment" in dashboard

        dff_entry = next(
            e for items in dashboard.values() for e in items if e["series_id"] == "DFF"
        )
        assert dff_entry["value"] == 4.33


class TestYieldSpread:
    def test_yield_spread(self, db):
        db.upsert_macro_indicator("T10Y2Y", "2026-02-20", 0.25)
        db.upsert_macro_indicator("T10Y3M", "2026-02-20", -0.15)

        spreads = get_yield_spread(db)
        assert spreads["T10Y2Y"]["inverted"] is False
        assert spreads["T10Y3M"]["inverted"] is True

    def test_yield_spread_empty(self, db):
        spreads = get_yield_spread(db)
        assert spreads == {}


class TestInflationTrend:
    def test_inflation_yoy(self, db):
        # Insert 13 months of CPI data
        for i in range(13):
            month = 13 - i
            year = 2025 if month <= 12 else 2026
            m = month if month <= 12 else month - 12
            val = 300.0 + i * 0.5
            db.upsert_macro_indicator("CPIAUCSL", f"{year}-{m:02d}-01", val)

        trend = get_inflation_trend(db, months=12)
        assert "CPIAUCSL" in trend
        assert "yoy_pct" in trend["CPIAUCSL"]

    def test_inflation_insufficient_data(self, db):
        db.upsert_macro_indicator("CPIAUCSL", "2026-01-01", 310.0)
        trend = get_inflation_trend(db)
        # Only 1 row, need at least 2
        assert "CPIAUCSL" not in trend
