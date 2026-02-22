#!/usr/bin/env python3
"""Track B: Comprehensive daily portfolio analysis.

Full market data refresh, technical indicator computation, all trigger checks,
trend/risk analysis, and butterfly chain detection. Run after market close.

Usage:
    python scripts/daily_analysis.py                  # full run (collect + analyze)
    python scripts/daily_analysis.py --skip-collection # analyze existing DB data
    python scripts/daily_analysis.py --days 90        # custom lookback period
    python scripts/daily_analysis.py --json           # JSON output
    python scripts/daily_analysis.py --no-color       # no ANSI colors

Exit codes:
    0 = no triggers fired
    1 = trigger(s) fired (action needed)
    2 = error
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_config import (
    HELD_TICKERS,
    MARKET_TICKERS,
    POSITIONS,
    INVESTED,
    REMAINING,
    TOTAL_CAPITAL,
    TRANCHE_2_TRADES,
    TRANCHE_3_TRADES,
    Colors,
    check_tranche_2_triggers,
    check_tranche_3_triggers,
    compute_pnl,
)

from src.database.operations import DatabaseOperations
from src.database.schema import init_db
from src.collection.market_data import collect_market_data
from src.collection.macro_data import collect_all_macro
from src.collection.crypto_data import collect_crypto_data
from src.utils.config import STOCK_TICKERS, DB_PATH, DATA_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DAILY_LOGS_DIR = DATA_DIR / "daily_logs"

# ──────────────────────────────────────────────────────────────
# DB + Collection
# ──────────────────────────────────────────────────────────────


def ensure_db() -> DatabaseOperations:
    """Ensure DB exists and return operations instance."""
    if not DB_PATH.exists():
        logger.info("Database not found, initializing...")
        init_db()
    return DatabaseOperations()


def collect_all_data(db: DatabaseOperations, days: int) -> dict[str, int]:
    """Collect market data for all asset classes."""
    results: dict[str, int] = {}

    logger.info("Collecting stock/index data...")
    try:
        results.update(collect_market_data(db, tickers=STOCK_TICKERS, period_days=days))
    except Exception as e:
        logger.warning(f"Stock collection error: {e}")

    logger.info("Collecting macro data (bonds, commodities, FX)...")
    try:
        results.update(collect_all_macro(db, period_days=days))
    except Exception as e:
        logger.warning(f"Macro collection error: {e}")

    logger.info("Collecting crypto data...")
    try:
        results.update(collect_crypto_data(db, period_days=days))
    except Exception as e:
        logger.warning(f"Crypto collection error: {e}")

    total = sum(results.values())
    successful = sum(1 for v in results.values() if v > 0)
    logger.info(f"Collection complete: {total} rows for {successful}/{len(results)} tickers")
    return results


def compute_technical_indicators(db: DatabaseOperations) -> int:
    """Compute technical indicators for all assets. Returns count of updated assets."""
    try:
        from src.collection.technical_indicators import update_indicators_in_db
    except ImportError:
        logger.warning("pandas_ta not available, skipping indicator computation")
        return 0

    updated = 0
    assets = db.get_all_assets()
    for asset in assets:
        try:
            count = update_indicators_in_db(db, asset["id"])
            if count > 0:
                updated += 1
        except Exception as e:
            logger.warning(f"Indicator computation failed for {asset['ticker']}: {e}")

    logger.info(f"Indicators updated for {updated}/{len(assets)} assets")
    return updated


# ──────────────────────────────────────────────────────────────
# Indicator Extraction from DB
# ──────────────────────────────────────────────────────────────


def get_held_stock_indicators(db: DatabaseOperations) -> dict:
    """Fetch latest technical indicators for held stocks from DB.

    Returns dict with keys: prices, rsi_values, macd_data, sma_data
    """
    prices = {}
    rsi_values = {}
    macd_data = {}
    sma_data = {}

    for ticker in HELD_TICKERS:
        asset_id = db.get_asset_id(ticker)
        if asset_id is None:
            logger.warning(f"Asset {ticker} not found in DB")
            continue

        rows = db.get_market_data(asset_id, limit=2)
        if not rows:
            logger.warning(f"No market data for {ticker}")
            continue

        latest = rows[0]
        prev = rows[1] if len(rows) >= 2 else None

        # Current price
        close = latest.get("close") or latest.get("adj_close")
        if close is not None:
            prices[ticker] = float(close)

        # RSI
        rsi = latest.get("rsi_14")
        rsi_values[ticker] = float(rsi) if rsi is not None else None

        # MACD (need current + previous for golden cross detection)
        macd_val = latest.get("macd")
        signal_val = latest.get("macd_signal")
        if macd_val is not None and signal_val is not None and prev is not None:
            prev_macd = prev.get("macd")
            prev_signal = prev.get("macd_signal")
            macd_data[ticker] = {
                "macd": float(macd_val),
                "signal": float(signal_val),
                "prev_macd": float(prev_macd) if prev_macd is not None else None,
                "prev_signal": float(prev_signal) if prev_signal is not None else None,
            }
        else:
            macd_data[ticker] = None

        # SMA20
        sma_20 = latest.get("sma_20")
        if close is not None and sma_20 is not None:
            sma_data[ticker] = {
                "close": float(close),
                "sma_20": float(sma_20),
            }
        else:
            sma_data[ticker] = None

    return {
        "prices": prices,
        "rsi_values": rsi_values,
        "macd_data": macd_data,
        "sma_data": sma_data,
    }


def get_market_overview(db: DatabaseOperations) -> dict:
    """Get S&P 500 and VIX latest data."""
    overview = {}
    for ticker in MARKET_TICKERS:
        asset_id = db.get_asset_id(ticker)
        if asset_id is None:
            continue
        rows = db.get_market_data(asset_id, limit=2)
        if not rows:
            continue
        latest = rows[0]
        prev = rows[1] if len(rows) >= 2 else None
        close = latest.get("close") or latest.get("adj_close")
        prev_close = (prev.get("close") or prev.get("adj_close")) if prev else None
        if close is not None:
            change_pct = ((close - prev_close) / prev_close * 100) if prev_close else 0.0
            overview[ticker] = {
                "price": float(close),
                "prev_close": float(prev_close) if prev_close else None,
                "change_pct": change_pct,
                "date": latest.get("date", ""),
            }
    return overview


# ──────────────────────────────────────────────────────────────
# Analysis Functions
# ──────────────────────────────────────────────────────────────


def run_trend_analysis(db: DatabaseOperations) -> dict:
    """Run trend signal detection."""
    try:
        from src.analysis.trend_detector import get_all_trend_signals
        return get_all_trend_signals(db)
    except Exception as e:
        logger.warning(f"Trend analysis failed: {e}")
        return {}


def run_risk_assessment(db: DatabaseOperations) -> dict:
    """Run risk assessment."""
    try:
        from src.analysis.risk_assessor import assess_market_risk
        return assess_market_risk(db)
    except Exception as e:
        logger.warning(f"Risk assessment failed: {e}")
        return {}


def run_butterfly_detection(db: DatabaseOperations) -> list[dict]:
    """Detect active butterfly chains."""
    try:
        from src.database.queries import AnalyticalQueries
        qt = AnalyticalQueries(db)
        return qt.butterfly_chains_active(min_confidence=0.1)
    except Exception as e:
        logger.warning(f"Butterfly chain detection failed: {e}")
        return []


# ──────────────────────────────────────────────────────────────
# Report Generation
# ──────────────────────────────────────────────────────────────


def generate_markdown_report(
    now: datetime,
    market_overview: dict,
    pnl_list: list[dict],
    indicators: dict,
    t2_result,
    t3_result,
    trend_signals: dict,
    risk_data: dict,
    butterfly_chains: list[dict],
) -> str:
    """Generate markdown daily report."""
    lines = []
    date_str = now.strftime("%Y-%m-%d")

    lines.append(f"# Daily Portfolio Analysis — {date_str}")
    lines.append("")
    lines.append(f"*Generated: {now.strftime('%Y-%m-%d %H:%M')} KST*")
    lines.append("")

    # Market Overview
    lines.append("## Market Overview")
    lines.append("")
    sp = market_overview.get("^GSPC", {})
    vix = market_overview.get("^VIX", {})
    if sp:
        lines.append(f"- **S&P 500**: {sp['price']:,.0f} ({sp['change_pct']:+.1f}%)")
    if vix:
        vix_level = "elevated" if vix["price"] > 20 else "normal"
        lines.append(f"- **VIX**: {vix['price']:.1f} ({vix_level})")
    lines.append("")

    # Portfolio P&L
    lines.append("## Portfolio P&L")
    lines.append("")
    lines.append("| 종목 | 주수 | 매수가 | 현재가 | P&L | 수익률 |")
    lines.append("|------|------|--------|--------|-----|--------|")
    for item in pnl_list:
        if item["ticker"] == "TOTAL":
            lines.append(
                f"| **합계** | {item['shares']} |  |  "
                f"| **{item['pnl']:+,.2f}** | **{item['pnl_pct']:+.1f}%** |"
            )
        else:
            lines.append(
                f"| {item['ticker']} | {item['shares']} "
                f"| ${item['avg_price']:,.2f} | ${item['current_price']:,.2f} "
                f"| {item['pnl']:+,.2f} | {item['pnl_pct']:+.1f}% |"
            )
    lines.append("")

    # Technical Indicators
    lines.append("## Technical Indicators")
    lines.append("")
    lines.append("| 종목 | RSI(14) | MACD | Signal | SMA20 | Close vs SMA20 |")
    lines.append("|------|---------|------|--------|-------|----------------|")
    rsi = indicators.get("rsi_values", {})
    macd = indicators.get("macd_data", {})
    sma = indicators.get("sma_data", {})
    for ticker in HELD_TICKERS:
        rsi_val = rsi.get(ticker)
        rsi_str = f"{rsi_val:.1f}" if rsi_val is not None else "N/A"
        m = macd.get(ticker)
        macd_str = f"{m['macd']:.3f}" if m and m.get("macd") is not None else "N/A"
        sig_str = f"{m['signal']:.3f}" if m and m.get("signal") is not None else "N/A"
        s = sma.get(ticker)
        sma_str = f"${s['sma_20']:,.2f}" if s and s.get("sma_20") is not None else "N/A"
        vs = ""
        if s and s.get("close") is not None and s.get("sma_20") is not None:
            vs = "above" if s["close"] > s["sma_20"] else "below"
        lines.append(f"| {ticker} | {rsi_str} | {macd_str} | {sig_str} | {sma_str} | {vs} |")
    lines.append("")

    # Trigger Status
    lines.append("## Split-Buy Trigger Status")
    lines.append("")
    lines.append("### Tranche 2")
    lines.append("")
    for t in t2_result.triggers:
        icon = "✓" if t.fired is True else "✗" if t.fired is False else "—"
        lines.append(f"- {icon} **{t.name}**: {t.details}")
    lines.append(f"- **Result**: {t2_result.summary}")
    lines.append("")

    lines.append("### Tranche 3")
    lines.append("")
    for t in t3_result.triggers:
        icon = "✓" if t.fired is True else "✗" if t.fired is False else "—"
        lines.append(f"- {icon} **{t.name}**: {t.details}")
    lines.append(f"- **Result**: {t3_result.summary}")
    lines.append("")

    # Trend Signals (for held stocks)
    lines.append("## Trend Signals (Held Stocks)")
    lines.append("")
    for ticker in HELD_TICKERS:
        signals = trend_signals.get(ticker, [])
        if signals:
            lines.append(f"### {ticker}")
            for sig in signals[:5]:
                sig_type = sig.get("type", "unknown")
                description = sig.get("description", "")
                signal_dir = sig.get("signal", "")
                lines.append(f"- **{sig_type}** ({signal_dir}): {description}")
            lines.append("")
        else:
            lines.append(f"### {ticker}")
            lines.append("- No active signals")
            lines.append("")

    # Risk Assessment
    if risk_data:
        lines.append("## Risk Assessment")
        lines.append("")
        overall = risk_data.get("overall_risk", "unknown")
        score = risk_data.get("risk_score", 0)
        lines.append(f"- **Overall Market Risk**: {overall} (score: {score:.2f})")
        high_risk = risk_data.get("high_risk_assets", [])
        if high_risk:
            lines.append(f"- **High Risk Assets**: {', '.join(a.get('ticker', str(a)) for a in high_risk[:5])}")
        lines.append("")

    # Butterfly Chains
    if butterfly_chains:
        lines.append("## Active Butterfly Chains")
        lines.append("")
        for chain in butterfly_chains[:5]:
            name = chain.get("name", "Unknown")
            confidence = chain.get("confidence", 0)
            detail = chain.get("chain_detail", "")
            lines.append(f"### {name} (confidence: {confidence:.2f})")
            if detail:
                lines.append(f"```\n{detail}\n```")
            lines.append("")

    # Disclaimer
    lines.append("---")
    lines.append("")
    lines.append("*면책 조항: 본 분석은 데이터 기반 정보 제공 목적이며, 투자 조언이 아닙니다.*")

    return "\n".join(lines)


def format_terminal_summary(
    now: datetime,
    market_overview: dict,
    pnl_list: list[dict],
    indicators: dict,
    t2_result,
    t3_result,
    risk_data: dict,
    report_path: str | None,
) -> str:
    """Format concise terminal summary."""
    C = Colors
    SEP = "═" * 62
    THIN = "─" * 62
    lines = []

    lines.append(f"{C.BOLD}{SEP}{C.RESET}")
    lines.append(f"{C.BOLD} DAILY ANALYSIS  {now.strftime('%Y-%m-%d %H:%M')} KST{C.RESET}")
    lines.append(f"{C.BOLD}{SEP}{C.RESET}")

    # Market
    sp = market_overview.get("^GSPC", {})
    vix = market_overview.get("^VIX", {})
    parts = []
    if sp:
        c = C.GREEN if sp.get("change_pct", 0) >= 0 else C.RED
        parts.append(f"S&P 500: {sp['price']:,.0f} ({c}{sp['change_pct']:+.1f}%{C.RESET})")
    if vix:
        vc = C.RED if vix["price"] > 25 else C.YELLOW if vix["price"] > 20 else C.GREEN
        vix_level = "elevated" if vix["price"] > 20 else "normal"
        parts.append(f"VIX: {vc}{vix['price']:.1f}{C.RESET} ({vix_level})")
    if parts:
        lines.append(" " + "  |  ".join(parts))
        lines.append(THIN)

    # P&L
    for item in pnl_list:
        ticker = item["ticker"]
        pc = C.pnl_color(item["pnl"])
        if ticker == "TOTAL":
            lines.append(THIN)
            lines.append(
                f" {C.BOLD}TOTAL{C.RESET}   {item['shares']}주"
                f"  ${item['cost']:,.2f} → ${item['market_value']:,.2f}"
                f"  {pc}{item['pnl']:+,.2f}  ({item['pnl_pct']:+.1f}%){C.RESET}"
            )
        else:
            lines.append(
                f" {ticker:<6} {item['shares']}주"
                f"  ${item['avg_price']:,.2f} → ${item['current_price']:,.2f}"
                f"   {pc}{item['pnl']:+,.2f}  ({item['pnl_pct']:+.1f}%){C.RESET}"
            )

    lines.append("")

    # Technical indicators (compact)
    rsi = indicators.get("rsi_values", {})
    sma = indicators.get("sma_data", {})
    ind_parts = []
    for ticker in HELD_TICKERS:
        r = rsi.get(ticker)
        r_str = f"{r:.0f}" if r is not None else "N/A"
        s = sma.get(ticker)
        s_str = ""
        if s and s.get("close") is not None and s.get("sma_20") is not None:
            s_str = "↑SMA20" if s["close"] > s["sma_20"] else "↓SMA20"
        ind_parts.append(f"{ticker}: RSI {r_str} {s_str}")
    lines.append(f" {C.DIM}{'  |  '.join(ind_parts)}{C.RESET}")
    lines.append("")

    # Trigger status
    for result, label in [(t2_result, "2차 매수"), (t3_result, "3차 매수")]:
        parts = []
        for t in result.triggers:
            if t.fired is True:
                parts.append(f"{C.GREEN}✓ {t.name}{C.RESET}")
            elif t.fired is False:
                if t.name == "price_drop_5pct":
                    md = t.data.get("max_drop_pct", 0)
                    parts.append(f"✗ 5% 하락 ({md:+.1f}%)")
                elif t.name == "time_elapsed":
                    d = t.data.get("days_remaining", "?")
                    parts.append(f"✗ {t.data.get('target_date', '')}까지 {d}일")
                elif t.name == "rsi_recovery":
                    cnt = len(t.data.get("recovered_tickers", {}))
                    mn = t.data.get("min_stocks", 2)
                    parts.append(f"✗ RSI≥45 ({cnt}/{mn})")
                elif t.name == "macd_golden_cross":
                    cnt = len(t.data.get("crossed_tickers", {}))
                    mn = t.data.get("min_stocks", 2)
                    parts.append(f"✗ MACD cross ({cnt}/{mn})")
                elif t.name == "sma20_recapture":
                    cnt = len(t.data.get("above_sma20", {}))
                    mn = t.data.get("min_stocks", 2)
                    parts.append(f"✗ SMA20 탈환 ({cnt}/{mn})")
                else:
                    parts.append(f"✗ {t.name}")
            elif t.fired is None:
                parts.append(f"{C.DIM}— {t.name}{C.RESET}")

        lbl = f"{C.GREEN}{C.BOLD}{label}{C.RESET}" if result.any_fired else f" {label}"
        lines.append(f"{lbl}: {' | '.join(parts)}")

    fired_any = t2_result.any_fired or t3_result.any_fired
    if fired_any:
        lines.append(f" → {C.GREEN}{C.BOLD}트리거 충족! 매수 검토 필요{C.RESET}")
    else:
        lines.append(f" → 대기 유지")

    # Risk
    if risk_data:
        overall = risk_data.get("overall_risk", "unknown")
        score = risk_data.get("risk_score", 0)
        rc = C.RED if score > 0.6 else C.YELLOW if score > 0.4 else C.GREEN
        lines.append(f"\n {C.DIM}Market Risk:{C.RESET} {rc}{overall} ({score:.2f}){C.RESET}")

    # Report path
    if report_path:
        lines.append(f"\n {C.DIM}Report saved: {report_path}{C.RESET}")

    lines.append(f"{C.BOLD}{SEP}{C.RESET}")
    return "\n".join(lines)


def build_json_output(
    now: datetime,
    market_overview: dict,
    pnl_list: list[dict],
    indicators: dict,
    t2_result,
    t3_result,
    trend_signals: dict,
    risk_data: dict,
    butterfly_chains: list[dict],
    report_path: str | None,
) -> dict:
    """Build JSON-serializable output."""
    def serialize_tranche(result):
        return {
            "tranche": result.tranche,
            "any_fired": result.any_fired,
            "triggers": [
                {"name": t.name, "fired": t.fired, "details": t.details, "data": t.data}
                for t in result.triggers
            ],
            "summary": result.summary,
        }

    # Filter trend signals to held stocks
    held_trends = {t: trend_signals.get(t, []) for t in HELD_TICKERS}

    return {
        "timestamp": now.isoformat(),
        "market_overview": market_overview,
        "positions": [item for item in pnl_list if item["ticker"] != "TOTAL"],
        "total": next((item for item in pnl_list if item["ticker"] == "TOTAL"), None),
        "indicators": {
            "rsi": indicators.get("rsi_values", {}),
            "macd": {k: v for k, v in indicators.get("macd_data", {}).items() if v is not None},
            "sma20": {k: v for k, v in indicators.get("sma_data", {}).items() if v is not None},
        },
        "tranche_2": serialize_tranche(t2_result),
        "tranche_3": serialize_tranche(t3_result),
        "trend_signals": held_trends,
        "risk": risk_data,
        "butterfly_chains": [
            {"name": c.get("name"), "confidence": c.get("confidence"),
             "detail": c.get("chain_detail")}
            for c in butterfly_chains[:5]
        ],
        "action_needed": t2_result.any_fired or t3_result.any_fired,
        "report_path": report_path,
    }


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Daily portfolio analysis (Track B)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--skip-collection", action="store_true", help="Skip data collection")
    parser.add_argument("--days", type=int, default=90, help="Collection lookback days (default 90)")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    args = parser.parse_args()

    if args.no_color or args.json:
        Colors.disable()

    now = datetime.now()

    # 1. Ensure DB
    try:
        db = ensure_db()
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        if args.json:
            print(json.dumps({"error": str(e), "timestamp": now.isoformat()}))
        sys.exit(2)

    # 2. Data collection
    if not args.skip_collection:
        logger.info(f"Collecting market data ({args.days} days)...")
        collect_all_data(db, args.days)

        logger.info("Computing technical indicators...")
        compute_technical_indicators(db)
    else:
        logger.info("Skipping data collection (--skip-collection)")

    # 3. Get indicators for held stocks
    logger.info("Fetching held stock indicators...")
    indicators = get_held_stock_indicators(db)
    prices = indicators["prices"]
    rsi_values = indicators["rsi_values"]
    macd_data = indicators["macd_data"]
    sma_data = indicators["sma_data"]

    if not prices:
        msg = "No price data available for held stocks"
        logger.error(msg)
        if args.json:
            print(json.dumps({"error": msg, "timestamp": now.isoformat()}))
        sys.exit(2)

    # 4. Market overview
    market_overview = get_market_overview(db)

    # 5. P&L
    pnl_list = compute_pnl(POSITIONS, prices)

    # 6. All trigger checks (full precision)
    t2_result = check_tranche_2_triggers(prices, rsi_values)
    t3_result = check_tranche_3_triggers(prices, macd_data, sma_data)

    # 7. Trend signals
    logger.info("Running trend analysis...")
    trend_signals = run_trend_analysis(db)

    # 8. Risk assessment
    logger.info("Running risk assessment...")
    risk_data = run_risk_assessment(db)

    # 9. Butterfly chains
    logger.info("Checking butterfly chains...")
    butterfly_chains = run_butterfly_detection(db)

    # 10. Generate & save markdown report
    report_path = None
    try:
        DAILY_LOGS_DIR.mkdir(parents=True, exist_ok=True)
        date_str = now.strftime("%Y%m%d")
        report_file = DAILY_LOGS_DIR / f"daily_{date_str}.md"
        report_md = generate_markdown_report(
            now, market_overview, pnl_list, indicators,
            t2_result, t3_result, trend_signals, risk_data, butterfly_chains,
        )
        report_file.write_text(report_md, encoding="utf-8")
        report_path = str(report_file)
        logger.info(f"Report saved to {report_path}")
    except Exception as e:
        logger.warning(f"Failed to save report: {e}")

    # 11. Output
    if args.json:
        output = build_json_output(
            now, market_overview, pnl_list, indicators,
            t2_result, t3_result, trend_signals, risk_data,
            butterfly_chains, report_path,
        )
        print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
    else:
        print(format_terminal_summary(
            now, market_overview, pnl_list, indicators,
            t2_result, t3_result, risk_data, report_path,
        ))

    # Exit code
    if t2_result.any_fired or t3_result.any_fired:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
