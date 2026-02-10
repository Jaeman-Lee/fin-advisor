"""Tests for theme categorization module."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.processing.categorizer import match_keywords, categorize_item, get_best_theme
from src.database.schema import init_db
from src.database.operations import DatabaseOperations


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return DatabaseOperations(db_path)


class TestMatchKeywords:
    def test_full_match(self):
        score = match_keywords("fed rate hike decision", "fed,rate,hike")
        assert score == 1.0

    def test_partial_match(self):
        score = match_keywords("fed announces decision", "fed,rate,hike")
        assert 0.0 < score < 1.0

    def test_no_match(self):
        score = match_keywords("apple releases new iphone", "fed,rate,hike")
        assert score == 0.0

    def test_empty_text(self):
        assert match_keywords("", "fed,rate") == 0.0

    def test_empty_keywords(self):
        assert match_keywords("some text", "") == 0.0

    def test_case_insensitive(self):
        score = match_keywords("FED RATE HIKE", "fed,rate,hike")
        assert score == 1.0


class TestCategorizeItem:
    def test_macro_categorization(self, db):
        matches = categorize_item(db, "Federal Reserve raises interest rate by 25bps")
        assert len(matches) > 0
        # Should match "Interest Rates" theme in macro category
        top = matches[0]
        assert top["category"] == "macro"

    def test_geopolitics_categorization(self, db):
        matches = categorize_item(db, "US-China trade war escalates with new tariffs")
        assert len(matches) > 0
        categories = [m["category"] for m in matches]
        assert "geopolitics" in categories

    def test_sector_categorization(self, db):
        matches = categorize_item(db, "NVIDIA GPU demand surges amid AI boom")
        assert len(matches) > 0
        categories = [m["category"] for m in matches]
        assert "sector" in categories

    def test_no_match(self, db):
        matches = categorize_item(db, "Random unrelated topic about cooking recipes")
        # May have some weak matches, but should be low scoring
        if matches:
            assert matches[0]["score"] < 0.5


class TestGetBestTheme:
    def test_returns_best(self, db):
        best = get_best_theme(db, "Bitcoin crypto blockchain rally")
        assert best is not None
        assert best["category"] == "asset"

    def test_returns_none_for_irrelevant(self, db):
        best = get_best_theme(db, "xyzzy plugh gibbrsh qqq")
        assert best is None
