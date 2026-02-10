"""CRUD operations for the investment advisory database."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from src.database.schema import get_connection
from src.utils.config import DB_PATH


class DatabaseOperations:
    """Encapsulates all database CRUD operations."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DB_PATH

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self.db_path)

    # ── Data Sources ───────────────────────────────────────────────────────

    def get_source_id(self, name: str) -> int | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM data_sources WHERE name = ?", (name,)
            ).fetchone()
            return row["id"] if row else None

    def upsert_data_source(self, name: str, source_type: str,
                           description: str = "", base_url: str | None = None) -> int:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO data_sources (name, source_type, base_url, description)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                     source_type=excluded.source_type,
                     base_url=excluded.base_url,
                     description=excluded.description,
                     updated_at=datetime('now')""",
                (name, source_type, base_url, description),
            )
            row = conn.execute(
                "SELECT id FROM data_sources WHERE name = ?", (name,)
            ).fetchone()
            return row["id"]

    # ── Asset Registry ─────────────────────────────────────────────────────

    def upsert_asset(self, ticker: str, name: str, asset_type: str,
                     exchange: str | None = None, currency: str = "USD") -> int:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO asset_registry (ticker, name, asset_type, exchange, currency)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(ticker) DO UPDATE SET
                     name=excluded.name,
                     asset_type=excluded.asset_type,
                     exchange=excluded.exchange,
                     currency=excluded.currency""",
                (ticker, name, asset_type, exchange, currency),
            )
            row = conn.execute(
                "SELECT id FROM asset_registry WHERE ticker = ?", (ticker,)
            ).fetchone()
            return row["id"]

    def get_asset_id(self, ticker: str) -> int | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM asset_registry WHERE ticker = ?", (ticker,)
            ).fetchone()
            return row["id"] if row else None

    def get_all_assets(self, asset_type: str | None = None) -> list[dict]:
        with self._conn() as conn:
            if asset_type:
                rows = conn.execute(
                    "SELECT * FROM asset_registry WHERE asset_type = ? AND is_active = 1",
                    (asset_type,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM asset_registry WHERE is_active = 1"
                ).fetchall()
            return [dict(r) for r in rows]

    # ── Raw Data Items ─────────────────────────────────────────────────────

    def insert_raw_item(self, source_id: int, title: str, data_type: str,
                        content: str | None = None, url: str | None = None,
                        published_at: str | None = None,
                        raw_json: str | None = None,
                        content_hash: str | None = None) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO raw_data_items
                   (source_id, title, content, url, published_at, data_type, raw_json, content_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (source_id, title, content, url, published_at, data_type, raw_json, content_hash),
            )
            return cur.lastrowid

    def check_hash_exists(self, content_hash: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM raw_data_items WHERE content_hash = ?", (content_hash,)
            ).fetchone()
            return row is not None

    def get_unprocessed_items(self, limit: int = 100) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM raw_data_items WHERE is_processed = 0 ORDER BY collected_at LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_as_processed(self, item_id: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE raw_data_items SET is_processed = 1 WHERE id = ?", (item_id,)
            )

    # ── Themes ─────────────────────────────────────────────────────────────

    def get_themes(self, category: str | None = None) -> list[dict]:
        with self._conn() as conn:
            if category:
                rows = conn.execute(
                    "SELECT * FROM themes WHERE category = ?", (category,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM themes").fetchall()
            return [dict(r) for r in rows]

    def get_theme_id(self, category: str, name: str) -> int | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM themes WHERE category = ? AND name = ?",
                (category, name),
            ).fetchone()
            return row["id"] if row else None

    # ── Processed Data ─────────────────────────────────────────────────────

    def insert_processed_data(self, raw_item_id: int, title: str,
                              theme_id: int | None = None,
                              summary: str | None = None,
                              sentiment_score: float | None = None,
                              sentiment_label: str | None = None,
                              relevance_score: float | None = None,
                              impact_score: float | None = None,
                              affected_assets: list[str] | None = None) -> int:
        assets_json = json.dumps(affected_assets) if affected_assets else None
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO processed_data
                   (raw_item_id, theme_id, title, summary, sentiment_score,
                    sentiment_label, relevance_score, impact_score, affected_assets)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (raw_item_id, theme_id, title, summary, sentiment_score,
                 sentiment_label, relevance_score, impact_score, assets_json),
            )
            return cur.lastrowid

    def get_processed_data(self, theme_id: int | None = None,
                           min_relevance: float = 0.0,
                           limit: int = 100) -> list[dict]:
        with self._conn() as conn:
            query = "SELECT * FROM processed_data WHERE relevance_score >= ?"
            params: list = [min_relevance]
            if theme_id is not None:
                query += " AND theme_id = ?"
                params.append(theme_id)
            query += " ORDER BY processed_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    # ── Market Data ────────────────────────────────────────────────────────

    def upsert_market_data(self, asset_id: int, date: str,
                           open_: float | None = None, high: float | None = None,
                           low: float | None = None, close: float | None = None,
                           volume: float | None = None, adj_close: float | None = None) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO market_data (asset_id, date, open, high, low, close, volume, adj_close)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(asset_id, date) DO UPDATE SET
                     open=excluded.open, high=excluded.high, low=excluded.low,
                     close=excluded.close, volume=excluded.volume, adj_close=excluded.adj_close""",
                (asset_id, date, open_, high, low, close, volume, adj_close),
            )
            return cur.lastrowid

    def update_technical_indicators(self, asset_id: int, date: str, **indicators) -> None:
        allowed = {
            "sma_20", "sma_50", "sma_200", "rsi_14",
            "macd", "macd_signal", "macd_hist",
            "bb_upper", "bb_middle", "bb_lower",
        }
        filtered = {k: v for k, v in indicators.items() if k in allowed}
        if not filtered:
            return
        set_clause = ", ".join(f"{k} = ?" for k in filtered)
        values = list(filtered.values()) + [asset_id, date]
        with self._conn() as conn:
            conn.execute(
                f"UPDATE market_data SET {set_clause} WHERE asset_id = ? AND date = ?",
                values,
            )

    def get_market_data(self, asset_id: int, start_date: str | None = None,
                        end_date: str | None = None, limit: int = 500) -> list[dict]:
        with self._conn() as conn:
            query = "SELECT * FROM market_data WHERE asset_id = ?"
            params: list = [asset_id]
            if start_date:
                query += " AND date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND date <= ?"
                params.append(end_date)
            query += " ORDER BY date DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    # ── Butterfly Chains ───────────────────────────────────────────────────

    def create_butterfly_chain(self, name: str, trigger_event: str,
                               description: str | None = None,
                               final_impact: str | None = None,
                               confidence: float | None = None) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO butterfly_chains (name, description, trigger_event, final_impact, confidence)
                   VALUES (?, ?, ?, ?, ?)""",
                (name, description, trigger_event, final_impact, confidence),
            )
            return cur.lastrowid

    def add_chain_link(self, chain_id: int, seq_order: int,
                       cause: str, effect: str,
                       mechanism: str | None = None,
                       strength: float | None = None,
                       evidence_id: int | None = None) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO butterfly_chain_links
                   (chain_id, seq_order, cause, effect, mechanism, strength, evidence_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (chain_id, seq_order, cause, effect, mechanism, strength, evidence_id),
            )
            return cur.lastrowid

    def get_butterfly_chains(self, min_confidence: float = 0.0) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT bc.*, GROUP_CONCAT(bcl.cause || ' → ' || bcl.effect, ' | ') as chain_summary
                   FROM butterfly_chains bc
                   LEFT JOIN butterfly_chain_links bcl ON bc.id = bcl.chain_id
                   WHERE bc.confidence >= ?
                   GROUP BY bc.id
                   ORDER BY bc.confidence DESC""",
                (min_confidence,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Investment Signals ─────────────────────────────────────────────────

    def insert_signal(self, signal_type: str, strength: float, source_type: str,
                      asset_id: int | None = None, rationale: str | None = None,
                      supporting_data: dict | None = None,
                      valid_until: str | None = None) -> int:
        data_json = json.dumps(supporting_data) if supporting_data else None
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO investment_signals
                   (asset_id, signal_type, strength, source_type, rationale, supporting_data, valid_until)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (asset_id, signal_type, strength, source_type, rationale, data_json, valid_until),
            )
            return cur.lastrowid

    def get_active_signals(self, asset_id: int | None = None,
                           source_type: str | None = None) -> list[dict]:
        with self._conn() as conn:
            query = """SELECT s.*, a.ticker, a.name as asset_name
                       FROM investment_signals s
                       LEFT JOIN asset_registry a ON s.asset_id = a.id
                       WHERE (s.valid_until IS NULL OR s.valid_until >= datetime('now'))"""
            params: list = []
            if asset_id is not None:
                query += " AND s.asset_id = ?"
                params.append(asset_id)
            if source_type:
                query += " AND s.source_type = ?"
                params.append(source_type)
            query += " ORDER BY s.strength DESC"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    # ── Advisory Reports ───────────────────────────────────────────────────

    def insert_report(self, report_type: str, title: str,
                      executive_summary: str | None = None,
                      market_overview: str | None = None,
                      recommendations: dict | None = None,
                      risk_assessment: str | None = None,
                      signal_ids: list[int] | None = None) -> int:
        rec_json = json.dumps(recommendations) if recommendations else None
        sig_json = json.dumps(signal_ids) if signal_ids else None
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO advisory_reports
                   (report_type, title, executive_summary, market_overview,
                    recommendations, risk_assessment, signal_ids)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (report_type, title, executive_summary, market_overview,
                 rec_json, risk_assessment, sig_json),
            )
            return cur.lastrowid

    def get_latest_report(self, report_type: str | None = None) -> dict | None:
        with self._conn() as conn:
            query = "SELECT * FROM advisory_reports"
            params: list = []
            if report_type:
                query += " WHERE report_type = ?"
                params.append(report_type)
            query += " ORDER BY created_at DESC LIMIT 1"
            row = conn.execute(query, params).fetchone()
            return dict(row) if row else None

    # ── Generic Query ──────────────────────────────────────────────────────

    def execute_readonly(self, sql: str, params: tuple = ()) -> list[dict]:
        """Execute a read-only SQL query. Rejects any non-SELECT statement."""
        stripped = sql.strip().upper()
        if not stripped.startswith("SELECT"):
            raise ValueError("Only SELECT queries are allowed in read-only mode")
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
