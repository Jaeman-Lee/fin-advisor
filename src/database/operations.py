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

    # ── Portfolio Trades ───────────────────────────────────────────────────

    def insert_trade(self, asset_id: int, trade_date: str, action: str,
                     quantity: int, price: float, fees: float = 0,
                     tranche: int | None = None, strategy: str | None = None,
                     report_id: int | None = None, notes: str | None = None) -> int:
        total_cost = quantity * price + fees
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO portfolio_trades
                   (asset_id, trade_date, action, quantity, price, total_cost,
                    fees, tranche, strategy, report_id, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (asset_id, trade_date, action, quantity, price, total_cost,
                 fees, tranche, strategy, report_id, notes),
            )
            return cur.lastrowid

    def get_open_positions(self) -> list[dict]:
        """Get current portfolio positions with net quantities."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT a.ticker, a.name, a.asset_type,
                      SUM(CASE WHEN t.action='buy' THEN t.quantity ELSE -t.quantity END) as shares,
                      SUM(CASE WHEN t.action='buy' THEN t.total_cost ELSE -t.total_cost END) as total_cost,
                      ROUND(SUM(CASE WHEN t.action='buy' THEN t.total_cost ELSE -t.total_cost END)
                        / NULLIF(SUM(CASE WHEN t.action='buy' THEN t.quantity ELSE -t.quantity END), 0), 2) as avg_price,
                      t.strategy
                   FROM portfolio_trades t
                   JOIN asset_registry a ON t.asset_id = a.id
                   GROUP BY a.ticker, t.strategy
                   HAVING shares > 0
                   ORDER BY total_cost DESC"""
            ).fetchall()
            return [dict(r) for r in rows]

    def get_trades(self, strategy: str | None = None,
                   ticker: str | None = None) -> list[dict]:
        with self._conn() as conn:
            query = """SELECT t.*, a.ticker, a.name as asset_name
                       FROM portfolio_trades t
                       JOIN asset_registry a ON t.asset_id = a.id
                       WHERE 1=1"""
            params: list = []
            if strategy:
                query += " AND t.strategy = ?"
                params.append(strategy)
            if ticker:
                query += " AND a.ticker = ?"
                params.append(ticker)
            query += " ORDER BY t.trade_date DESC, t.created_at DESC"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    # ── Alert Log ─────────────────────────────────────────────────────────

    def log_alert(self, dedup_key: str, category: str, message: str,
                  ticker: str | None = None, priority: str = "INFO",
                  expires_at: str | None = None) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO alert_log
                   (dedup_key, category, ticker, priority, message, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (dedup_key, category, ticker, priority, message, expires_at),
            )
            return cur.lastrowid

    def is_alert_duplicate(self, dedup_key: str, hours: int = 24) -> bool:
        """Check if an alert with the same dedup_key was sent within `hours`.

        If the alert has expires_at=NULL (permanent), it's always a duplicate.
        """
        with self._conn() as conn:
            row = conn.execute(
                """SELECT 1 FROM alert_log
                   WHERE dedup_key = ?
                     AND (expires_at IS NULL
                          OR sent_at >= datetime('now', ?))
                   LIMIT 1""",
                (dedup_key, f"-{hours} hours"),
            ).fetchone()
            return row is not None

    # ── Macro Indicators (FRED) ────────────────────────────────────────────

    def upsert_macro_indicator(self, series_id: str, date: str,
                               value: float | None) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO macro_indicators (series_id, date, value)
                   VALUES (?, ?, ?)
                   ON CONFLICT(series_id, date) DO UPDATE SET
                     value=excluded.value,
                     updated_at=datetime('now')""",
                (series_id, date, value),
            )
            return cur.lastrowid

    def get_macro_series(self, series_id: str, start_date: str | None = None,
                         end_date: str | None = None,
                         limit: int = 1000) -> list[dict]:
        with self._conn() as conn:
            query = "SELECT * FROM macro_indicators WHERE series_id = ?"
            params: list = [series_id]
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

    def get_latest_macro_value(self, series_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT * FROM macro_indicators
                   WHERE series_id = ? AND value IS NOT NULL
                   ORDER BY date DESC LIMIT 1""",
                (series_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_macro_snapshot(self, series_ids: list[str] | None = None) -> list[dict]:
        """Get the latest value for each series (or specified subset)."""
        with self._conn() as conn:
            if series_ids:
                placeholders = ",".join("?" for _ in series_ids)
                rows = conn.execute(
                    f"""SELECT m.* FROM macro_indicators m
                        INNER JOIN (
                            SELECT series_id, MAX(date) as max_date
                            FROM macro_indicators
                            WHERE series_id IN ({placeholders}) AND value IS NOT NULL
                            GROUP BY series_id
                        ) latest ON m.series_id = latest.series_id AND m.date = latest.max_date""",
                    series_ids,
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT m.* FROM macro_indicators m
                       INNER JOIN (
                           SELECT series_id, MAX(date) as max_date
                           FROM macro_indicators WHERE value IS NOT NULL
                           GROUP BY series_id
                       ) latest ON m.series_id = latest.series_id AND m.date = latest.max_date"""
                ).fetchall()
            return [dict(r) for r in rows]

    # ── Event Queue ─────────────────────────────────────────────────────────

    def enqueue_event(self, event_type: str, ticker: str | None,
                      severity: str, payload: str,
                      description: str | None = None) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO event_queue
                   (event_type, ticker, severity, payload, description)
                   VALUES (?, ?, ?, ?, ?)""",
                (event_type, ticker, severity, payload, description),
            )
            return cur.lastrowid

    def get_pending_events(self, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM event_queue
                   WHERE processed = 0
                   ORDER BY detected_at ASC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_event_processed(self, event_id: int, result: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """UPDATE event_queue
                   SET processed = 1, processed_at = datetime('now'),
                       processor_result = ?
                   WHERE id = ?""",
                (result, event_id),
            )

    def mark_event_skipped(self, event_id: int, reason: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """UPDATE event_queue
                   SET processed = 2, processed_at = datetime('now'),
                       processor_result = ?
                   WHERE id = ?""",
                (reason, event_id),
            )

    def is_event_duplicate(self, event_type: str, ticker: str | None,
                           hours: int = 6) -> bool:
        with self._conn() as conn:
            if ticker:
                row = conn.execute(
                    """SELECT 1 FROM event_queue
                       WHERE event_type = ? AND ticker = ?
                         AND detected_at >= datetime('now', ?)
                       LIMIT 1""",
                    (event_type, ticker, f"-{hours} hours"),
                ).fetchone()
            else:
                row = conn.execute(
                    """SELECT 1 FROM event_queue
                       WHERE event_type = ? AND ticker IS NULL
                         AND detected_at >= datetime('now', ?)
                       LIMIT 1""",
                    (event_type, f"-{hours} hours"),
                ).fetchone()
            return row is not None

    # ── Generic Query ──────────────────────────────────────────────────────

    def execute_readonly(self, sql: str, params: tuple = ()) -> list[dict]:
        """Execute a read-only SQL query. Rejects any non-SELECT statement."""
        stripped = sql.strip().upper()
        if not stripped.startswith("SELECT"):
            raise ValueError("Only SELECT queries are allowed in read-only mode")
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
