"""Builds DebateContext by gathering data from existing DB and analysis modules."""

from __future__ import annotations

import logging
import sys

sys.path.insert(0, ".")

from src.database.operations import DatabaseOperations
from src.debate.models import DebateContext

logger = logging.getLogger(__name__)


def _safe_get(func, *args, default=None, **kwargs):
    """Call a function, return default on error."""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.debug("context_builder: %s failed: %s", func.__name__, e)
        return default


def build_context(
    db: DatabaseOperations,
    ticker: str,
    portfolio_config: dict | None = None,
) -> DebateContext:
    """Gather all available data for a ticker into a DebateContext.

    Args:
        db: Database operations instance.
        ticker: Asset ticker symbol.
        portfolio_config: Optional dict with portfolio-level info
            (position_pct, pnl_pct, vix, usdkrw, total_realized_loss_krw, etc.)
    """
    # Asset info
    asset_info = {}
    asset_id = None
    try:
        asset_id = db.get_asset_id(ticker)
        assets = db.get_all_assets()
        for a in assets:
            if a.get("ticker") == ticker:
                asset_info = dict(a)
                break
    except Exception:
        pass

    # Market data (recent 90 days)
    market_data = []
    if asset_id:
        raw = _safe_get(db.get_market_data, asset_id, limit=90, default=[])
        if raw:
            market_data = [dict(r) for r in raw]

    # Trend signals
    trend_signals = []
    try:
        from src.analysis.trend_detector import get_all_trend_signals
        all_trends = get_all_trend_signals(db)
        trend_signals = [t for t in all_trends if t.get("ticker") == ticker]
    except Exception:
        pass

    # Risk assessment
    risk_assessment = {}
    if asset_id:
        try:
            from src.analysis.risk_assessor import assess_asset_risk
            risk_assessment = assess_asset_risk(db, asset_id) or {}
        except Exception:
            pass

    # Sentiment data
    sentiment_data = []
    try:
        rows = db.execute_readonly(
            """
            SELECT title, sentiment_score, sentiment_label, relevance_score,
                   impact_score, affected_assets
            FROM processed_data
            WHERE affected_assets LIKE ?
            ORDER BY rowid DESC LIMIT 20
            """,
            (f"%{ticker}%",),
        )
        sentiment_data = [dict(r) for r in rows] if rows else []
    except Exception:
        pass

    # Macro snapshot
    macro_snapshot = []
    try:
        snapshot = db.get_macro_snapshot()
        macro_snapshot = [dict(r) for r in snapshot] if snapshot else []
    except Exception:
        pass

    # Active signals
    active_signals = []
    if asset_id:
        try:
            rows = db.execute_readonly(
                """
                SELECT signal_type, strength, source_type, rationale
                FROM investment_signals
                WHERE asset_id = ?
                ORDER BY rowid DESC LIMIT 10
                """,
                (asset_id,),
            )
            active_signals = [dict(r) for r in rows] if rows else []
        except Exception:
            pass

    # Fundamentals (from yfinance, cached per session)
    fundamentals = _fetch_fundamentals(ticker)

    return DebateContext(
        ticker=ticker,
        asset_info=asset_info,
        market_data=market_data,
        trend_signals=trend_signals,
        risk_assessment=risk_assessment,
        sentiment_data=sentiment_data,
        macro_snapshot=macro_snapshot,
        portfolio_context=portfolio_config or {},
        active_signals=active_signals,
        fundamentals=fundamentals,
    )


def _fetch_fundamentals(ticker: str) -> dict:
    """Fetch fundamentals from yfinance. Returns empty dict on failure."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.info or {}
        return {
            "forward_pe": info.get("forwardPE"),
            "trailing_pe": info.get("trailingPE"),
            "price_to_book": info.get("priceToBook"),
            "market_cap": info.get("marketCap"),
            "free_cashflow": info.get("freeCashflow"),
            "profit_margins": info.get("profitMargins"),
            "gross_margins": info.get("grossMargins"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "dividend_yield": info.get("dividendYield"),
            "payout_ratio": info.get("payoutRatio"),
            "debt_to_equity": info.get("debtToEquity"),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
            "target_mean_price": info.get("targetMeanPrice"),
            "recommendation_key": info.get("recommendationKey"),
            "short_name": info.get("shortName"),
        }
    except Exception as e:
        logger.debug("Failed to fetch fundamentals for %s: %s", ticker, e)
        return {}
