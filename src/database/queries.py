"""Pre-built analytical queries for the investment advisory system."""

from src.database.operations import DatabaseOperations


class AnalyticalQueries:
    """Collection of pre-built analytical queries."""

    def __init__(self, db: DatabaseOperations | None = None):
        self.db = db or DatabaseOperations()

    def latest_prices(self, asset_type: str | None = None, limit: int = 50) -> list[dict]:
        """Get latest prices for all tracked assets."""
        sql = """
            SELECT a.ticker, a.name, a.asset_type, m.date, m.close, m.volume,
                   m.rsi_14, m.sma_50, m.sma_200
            FROM market_data m
            JOIN asset_registry a ON m.asset_id = a.id
            WHERE m.date = (SELECT MAX(m2.date) FROM market_data m2 WHERE m2.asset_id = m.asset_id)
        """
        params: list = []
        if asset_type:
            sql += " AND a.asset_type = ?"
            params.append(asset_type)
        sql += " ORDER BY a.asset_type, a.ticker LIMIT ?"
        params.append(limit)
        return self.db.execute_readonly(sql, tuple(params))

    def price_change(self, days: int = 30) -> list[dict]:
        """Get price change % over the last N days for all assets."""
        sql = """
            SELECT a.ticker, a.name, a.asset_type,
                   latest.close AS current_price,
                   past.close AS past_price,
                   CASE WHEN past.close > 0
                        THEN ROUND((latest.close - past.close) / past.close * 100, 2)
                        ELSE NULL END AS change_pct
            FROM asset_registry a
            JOIN (
                SELECT asset_id, close, date
                FROM market_data
                WHERE (asset_id, date) IN (
                    SELECT asset_id, MAX(date) FROM market_data GROUP BY asset_id
                )
            ) latest ON a.id = latest.asset_id
            LEFT JOIN (
                SELECT asset_id, close, date
                FROM market_data
                WHERE date <= date('now', ?)
            ) past ON a.id = past.asset_id
                AND past.date = (
                    SELECT MAX(date) FROM market_data
                    WHERE asset_id = a.id AND date <= date('now', ?)
                )
            ORDER BY change_pct DESC
        """
        day_offset = f"-{days} days"
        return self.db.execute_readonly(sql, (day_offset, day_offset))

    def overbought_oversold(self) -> list[dict]:
        """Find assets with extreme RSI values (overbought >70, oversold <30)."""
        sql = """
            SELECT a.ticker, a.name, a.asset_type, m.date, m.close, m.rsi_14,
                   CASE WHEN m.rsi_14 >= 70 THEN 'overbought'
                        WHEN m.rsi_14 <= 30 THEN 'oversold'
                        ELSE 'neutral' END AS rsi_signal
            FROM market_data m
            JOIN asset_registry a ON m.asset_id = a.id
            WHERE m.date = (SELECT MAX(m2.date) FROM market_data m2 WHERE m2.asset_id = m.asset_id)
              AND m.rsi_14 IS NOT NULL
              AND (m.rsi_14 >= 70 OR m.rsi_14 <= 30)
            ORDER BY m.rsi_14 DESC
        """
        return self.db.execute_readonly(sql)

    def trend_analysis(self) -> list[dict]:
        """Analyze price trends using SMA crossovers."""
        sql = """
            SELECT a.ticker, a.name, a.asset_type, m.date, m.close,
                   m.sma_20, m.sma_50, m.sma_200,
                   CASE
                     WHEN m.close > m.sma_20 AND m.sma_20 > m.sma_50 AND m.sma_50 > m.sma_200
                       THEN 'strong_uptrend'
                     WHEN m.close > m.sma_50
                       THEN 'uptrend'
                     WHEN m.close < m.sma_20 AND m.sma_20 < m.sma_50 AND m.sma_50 < m.sma_200
                       THEN 'strong_downtrend'
                     WHEN m.close < m.sma_50
                       THEN 'downtrend'
                     ELSE 'sideways'
                   END AS trend
            FROM market_data m
            JOIN asset_registry a ON m.asset_id = a.id
            WHERE m.date = (SELECT MAX(m2.date) FROM market_data m2 WHERE m2.asset_id = m.asset_id)
              AND m.sma_50 IS NOT NULL
            ORDER BY a.asset_type, a.ticker
        """
        return self.db.execute_readonly(sql)

    def sentiment_summary(self, days: int = 7) -> list[dict]:
        """Get sentiment summary by theme for recent processed data."""
        sql = """
            SELECT t.category, t.name AS theme_name,
                   COUNT(*) AS item_count,
                   ROUND(AVG(p.sentiment_score), 3) AS avg_sentiment,
                   ROUND(AVG(p.impact_score), 3) AS avg_impact,
                   SUM(CASE WHEN p.sentiment_label IN ('positive','very_positive') THEN 1 ELSE 0 END) AS bullish_count,
                   SUM(CASE WHEN p.sentiment_label IN ('negative','very_negative') THEN 1 ELSE 0 END) AS bearish_count
            FROM processed_data p
            JOIN themes t ON p.theme_id = t.id
            WHERE p.processed_at >= datetime('now', ?)
            GROUP BY t.category, t.name
            ORDER BY avg_impact DESC
        """
        return self.db.execute_readonly(sql, (f"-{days} days",))

    def active_signals_summary(self) -> list[dict]:
        """Get summary of active investment signals."""
        sql = """
            SELECT s.signal_type, s.source_type,
                   a.ticker, a.name AS asset_name, a.asset_type,
                   s.strength, s.rationale,
                   s.valid_from, s.valid_until
            FROM investment_signals s
            LEFT JOIN asset_registry a ON s.asset_id = a.id
            WHERE s.valid_until IS NULL OR s.valid_until >= datetime('now')
            ORDER BY s.strength DESC
        """
        return self.db.execute_readonly(sql)

    def butterfly_chains_active(self, min_confidence: float = 0.1) -> list[dict]:
        """Get active butterfly chains with their links."""
        sql = """
            SELECT bc.id, bc.name, bc.trigger_event, bc.final_impact,
                   bc.confidence, bc.created_at,
                   GROUP_CONCAT(bcl.seq_order || '. ' || bcl.cause || ' → ' || bcl.effect, ' | ') AS chain_detail
            FROM butterfly_chains bc
            LEFT JOIN butterfly_chain_links bcl ON bc.id = bcl.chain_id
            WHERE bc.confidence >= ?
            GROUP BY bc.id
            ORDER BY bc.confidence DESC
        """
        return self.db.execute_readonly(sql, (min_confidence,))

    def asset_360_view(self, ticker: str) -> dict:
        """Get a comprehensive 360-degree view of a single asset.

        Returns dict with: price_data, signals, processed_news, trend.
        """
        asset_id_row = self.db.execute_readonly(
            "SELECT id FROM asset_registry WHERE ticker = ?", (ticker,)
        )
        if not asset_id_row:
            return {"error": f"Asset {ticker} not found"}

        asset_id = asset_id_row[0]["id"]

        price = self.db.execute_readonly(
            """SELECT date, close, volume, rsi_14, sma_20, sma_50, sma_200,
                      macd, macd_signal, bb_upper, bb_lower
               FROM market_data WHERE asset_id = ? ORDER BY date DESC LIMIT 30""",
            (asset_id,),
        )
        signals = self.db.execute_readonly(
            """SELECT signal_type, strength, source_type, rationale, valid_from
               FROM investment_signals
               WHERE asset_id = ? AND (valid_until IS NULL OR valid_until >= datetime('now'))
               ORDER BY strength DESC""",
            (asset_id,),
        )
        news = self.db.execute_readonly(
            f"""SELECT pd.title, pd.summary, pd.sentiment_score, pd.impact_score, pd.processed_at
               FROM processed_data pd
               WHERE pd.affected_assets LIKE ?
               ORDER BY pd.processed_at DESC LIMIT 10""",
            (f'%"{ticker}"%',),
        )

        return {
            "ticker": ticker,
            "recent_prices": price,
            "active_signals": signals,
            "recent_news": news,
        }

    def portfolio_signal_matrix(self) -> list[dict]:
        """Get cross-asset signal matrix for portfolio decisions."""
        sql = """
            SELECT a.asset_type,
                   a.ticker,
                   a.name,
                   m.close AS latest_price,
                   m.rsi_14,
                   CASE
                     WHEN m.close > m.sma_200 THEN 'above'
                     ELSE 'below'
                   END AS vs_sma200,
                   COALESCE(
                     (SELECT s.signal_type FROM investment_signals s
                      WHERE s.asset_id = a.id
                        AND (s.valid_until IS NULL OR s.valid_until >= datetime('now'))
                      ORDER BY s.strength DESC LIMIT 1),
                     'none'
                   ) AS top_signal,
                   COALESCE(
                     (SELECT ROUND(AVG(p.sentiment_score), 2) FROM processed_data p
                      WHERE p.affected_assets LIKE '%"' || a.ticker || '"%'
                        AND p.processed_at >= datetime('now', '-7 days')),
                     0
                   ) AS recent_sentiment
            FROM asset_registry a
            JOIN market_data m ON a.id = m.asset_id
            WHERE m.date = (SELECT MAX(m2.date) FROM market_data m2 WHERE m2.asset_id = a.id)
            ORDER BY a.asset_type, a.ticker
        """
        return self.db.execute_readonly(sql)
