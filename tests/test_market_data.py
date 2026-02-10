"""Tests for market data collection module."""

import sys
from pathlib import Path

import pytest
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collection.market_data import _safe_float, fetch_ohlcv, register_asset
from src.database.schema import init_db
from src.database.operations import DatabaseOperations


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return DatabaseOperations(db_path)


class TestSafeFloat:
    def test_normal_float(self):
        assert _safe_float(3.14) == 3.14

    def test_int(self):
        assert _safe_float(42) == 42.0

    def test_none(self):
        assert _safe_float(None) is None

    def test_nan(self):
        assert _safe_float(float("nan")) is None

    def test_string_number(self):
        assert _safe_float("3.14") == 3.14

    def test_invalid_string(self):
        assert _safe_float("not_a_number") is None


class TestFetchOHLCV:
    def test_fetch_valid_ticker(self):
        """Fetch a small amount of data for a well-known ticker."""
        df = fetch_ohlcv("AAPL", period_days=5)
        # May be empty on weekends/holidays, but should not error
        assert isinstance(df, pd.DataFrame)

    def test_fetch_invalid_ticker(self):
        """Invalid tickers should return empty DataFrame."""
        df = fetch_ohlcv("INVALID_TICKER_XYZ123", period_days=5)
        assert isinstance(df, pd.DataFrame)


class TestRegisterAsset:
    def test_register_known_type(self, db):
        aid = register_asset(db, "BTC-USD", asset_type="crypto")
        assert aid > 0
        asset = db.get_all_assets("crypto")
        assert len(asset) >= 1
        assert asset[0]["ticker"] == "BTC-USD"

    def test_register_auto_type(self, db):
        # Config has AAPL mapped to stock
        aid = register_asset(db, "AAPL")
        assert aid > 0
