"""Tests for database operations."""

import json
import pytest
from pathlib import Path
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database.schema import init_db, get_connection
from src.database.operations import DatabaseOperations


@pytest.fixture
def db(tmp_path):
    """Create a temporary test database."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return DatabaseOperations(db_path)


class TestDataSources:
    def test_default_sources_seeded(self, db):
        sid = db.get_source_id("yfinance")
        assert sid is not None

    def test_upsert_data_source(self, db):
        sid = db.upsert_data_source("test_source", "test", "A test source")
        assert sid > 0
        sid2 = db.get_source_id("test_source")
        assert sid == sid2

    def test_upsert_updates_existing(self, db):
        sid1 = db.upsert_data_source("src1", "type_a", "desc1")
        sid2 = db.upsert_data_source("src1", "type_b", "desc2")
        assert sid1 == sid2


class TestAssetRegistry:
    def test_upsert_asset(self, db):
        aid = db.upsert_asset("AAPL", "Apple Inc.", "stock", "NASDAQ", "USD")
        assert aid > 0

    def test_get_asset_id(self, db):
        db.upsert_asset("MSFT", "Microsoft", "stock")
        aid = db.get_asset_id("MSFT")
        assert aid is not None

    def test_get_asset_id_nonexistent(self, db):
        assert db.get_asset_id("NONEXIST") is None

    def test_get_all_assets_filtered(self, db):
        db.upsert_asset("AAPL", "Apple", "stock")
        db.upsert_asset("BTC-USD", "Bitcoin", "crypto")
        stocks = db.get_all_assets("stock")
        assert len(stocks) == 1
        assert stocks[0]["ticker"] == "AAPL"

    def test_get_all_assets_unfiltered(self, db):
        db.upsert_asset("AAPL", "Apple", "stock")
        db.upsert_asset("BTC-USD", "Bitcoin", "crypto")
        all_assets = db.get_all_assets()
        assert len(all_assets) == 2


class TestRawDataItems:
    def test_insert_and_check_hash(self, db):
        sid = db.get_source_id("websearch")
        rid = db.insert_raw_item(sid, "Test News", "news",
                                 content="Content", content_hash="abc123")
        assert rid > 0
        assert db.check_hash_exists("abc123")
        assert not db.check_hash_exists("xyz789")

    def test_unprocessed_items(self, db):
        sid = db.get_source_id("websearch")
        db.insert_raw_item(sid, "Item 1", "news")
        db.insert_raw_item(sid, "Item 2", "news")
        items = db.get_unprocessed_items()
        assert len(items) == 2

    def test_mark_as_processed(self, db):
        sid = db.get_source_id("websearch")
        rid = db.insert_raw_item(sid, "Item 1", "news")
        db.mark_as_processed(rid)
        items = db.get_unprocessed_items()
        assert len(items) == 0


class TestMarketData:
    def test_upsert_market_data(self, db):
        aid = db.upsert_asset("AAPL", "Apple", "stock")
        mid = db.upsert_market_data(aid, "2024-01-15",
                                     open_=180.0, high=185.0, low=179.0,
                                     close=183.0, volume=50000000)
        assert mid > 0

    def test_update_technical_indicators(self, db):
        aid = db.upsert_asset("AAPL", "Apple", "stock")
        db.upsert_market_data(aid, "2024-01-15", close=183.0)
        db.update_technical_indicators(aid, "2024-01-15",
                                        rsi_14=55.3, sma_20=181.0, sma_50=178.0)
        rows = db.get_market_data(aid)
        assert len(rows) == 1
        assert rows[0]["rsi_14"] == 55.3
        assert rows[0]["sma_20"] == 181.0

    def test_get_market_data_with_dates(self, db):
        aid = db.upsert_asset("AAPL", "Apple", "stock")
        for day in range(1, 6):
            db.upsert_market_data(aid, f"2024-01-{day:02d}", close=180.0 + day)
        rows = db.get_market_data(aid, start_date="2024-01-03", end_date="2024-01-04")
        assert len(rows) == 2


class TestProcessedData:
    def test_insert_and_get(self, db):
        sid = db.get_source_id("websearch")
        rid = db.insert_raw_item(sid, "Test", "news")
        pid = db.insert_processed_data(
            raw_item_id=rid, title="Processed Test",
            sentiment_score=0.5, sentiment_label="positive",
            relevance_score=0.8, impact_score=0.4,
            affected_assets=["AAPL", "MSFT"],
        )
        assert pid > 0
        results = db.get_processed_data(min_relevance=0.5)
        assert len(results) == 1
        assert results[0]["title"] == "Processed Test"


class TestInvestmentSignals:
    def test_insert_and_get_signal(self, db):
        aid = db.upsert_asset("AAPL", "Apple", "stock")
        sig_id = db.insert_signal(
            signal_type="buy", strength=0.8, source_type="technical",
            asset_id=aid, rationale="Golden cross",
        )
        assert sig_id > 0
        signals = db.get_active_signals(asset_id=aid)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "buy"


class TestButterflyChains:
    def test_create_chain_with_links(self, db):
        cid = db.create_butterfly_chain(
            name="Rate Hike Chain",
            trigger_event="Fed raises rates",
            final_impact="EM equities decline",
            confidence=0.5,
        )
        db.add_chain_link(cid, 1, "Fed raises rates", "USD strengthens",
                          mechanism="Capital inflows", strength=0.8)
        db.add_chain_link(cid, 2, "USD strengthens", "EM currencies weaken",
                          mechanism="Capital outflows", strength=0.7)
        chains = db.get_butterfly_chains(min_confidence=0.3)
        assert len(chains) == 1
        assert "chain_summary" in chains[0]


class TestReadonlyQuery:
    def test_select_allowed(self, db):
        result = db.execute_readonly("SELECT COUNT(*) as cnt FROM themes")
        assert result[0]["cnt"] > 0

    def test_insert_blocked(self, db):
        with pytest.raises(ValueError, match="SELECT"):
            db.execute_readonly("INSERT INTO themes (category, name) VALUES ('x', 'y')")

    def test_delete_blocked(self, db):
        with pytest.raises(ValueError, match="SELECT"):
            db.execute_readonly("DELETE FROM themes")


class TestAdvisoryReports:
    def test_insert_and_get_report(self, db):
        rid = db.insert_report(
            report_type="daily",
            title="Daily Report",
            executive_summary="All good",
            recommendations={"stock": 40, "bond": 30},
        )
        assert rid > 0
        report = db.get_latest_report("daily")
        assert report is not None
        assert report["title"] == "Daily Report"
