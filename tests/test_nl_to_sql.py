"""Tests for natural language to SQL conversion."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database.nl_to_sql import nl_to_sql, execute_nl_query, get_schema_context
from src.database.schema import init_db
from src.database.operations import DatabaseOperations


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return DatabaseOperations(db_path)


class TestNlToSql:
    def test_price_query(self):
        sql, params = nl_to_sql("What is the price of AAPL?")
        assert "SELECT" in sql.upper()
        assert "market_data" in sql

    def test_rsi_query(self):
        sql, params = nl_to_sql("Show me overbought assets by RSI")
        assert "rsi_14" in sql

    def test_sentiment_query(self):
        sql, params = nl_to_sql("What is the overall market sentiment?")
        assert "sentiment" in sql.lower()

    def test_signal_query(self):
        sql, params = nl_to_sql("What are the current buy signals?")
        assert "signal" in sql.lower()

    def test_trend_query(self):
        sql, params = nl_to_sql("Show me trend analysis for all assets")
        assert "sma" in sql.lower()

    def test_butterfly_query(self):
        sql, params = nl_to_sql("Show me butterfly chains")
        assert "butterfly_chain" in sql.lower()

    def test_crypto_query(self):
        sql, params = nl_to_sql("Show me all crypto prices")
        assert "crypto" in sql.lower()

    def test_default_query(self):
        sql, params = nl_to_sql("foobar unrecognized question xyz")
        assert "SELECT" in sql.upper()
        # Default overview query
        assert "count" in sql.lower() or "COUNT" in sql

    def test_all_queries_are_select(self):
        questions = [
            "Price of AAPL",
            "RSI signals",
            "Market sentiment",
            "Buy signals",
            "Trend analysis",
            "Butterfly chains",
            "Stock list all",
            "Crypto prices",
            "Unknown question",
        ]
        for q in questions:
            sql, _ = nl_to_sql(q)
            assert sql.strip().upper().startswith("SELECT"), f"Query for '{q}' is not SELECT"


class TestExecuteNlQuery:
    def test_execute_returns_structure(self, db):
        result = execute_nl_query(db, "Show all assets")
        assert "question" in result
        assert "sql" in result
        assert "results" in result
        assert "row_count" in result

    def test_execute_sentiment_empty_db(self, db):
        result = execute_nl_query(db, "What is the market sentiment?")
        assert result["row_count"] == 0  # no processed data yet

    def test_execute_with_seeded_data(self, db):
        # Themes are seeded, so this should return results
        result = execute_nl_query(db, "Show butterfly chains")
        # No chains yet, but query should execute without error
        assert "error" not in result


class TestSchemaContext:
    def test_schema_context_has_tables(self):
        ctx = get_schema_context()
        assert "asset_registry" in ctx
        assert "market_data" in ctx
        assert "processed_data" in ctx
        assert "investment_signals" in ctx
        assert "butterfly_chains" in ctx
