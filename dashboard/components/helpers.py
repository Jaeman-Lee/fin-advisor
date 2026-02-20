"""Shared helpers for the Streamlit dashboard."""

import sys
import subprocess
from pathlib import Path

import streamlit as st

# Ensure project root is on sys.path so `src.*` imports work.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.database.operations import DatabaseOperations
from src.database.queries import AnalyticalQueries


# ── Cached singletons ────────────────────────────────────────────────────────

@st.cache_resource
def get_db() -> DatabaseOperations:
    """Return a cached DatabaseOperations instance."""
    return DatabaseOperations()


def get_queries() -> AnalyticalQueries:
    """Return an AnalyticalQueries bound to the cached DB."""
    return AnalyticalQueries(get_db())


# ── i18n ──────────────────────────────────────────────────────────────────────

_TRANSLATIONS: dict[str, dict[str, str]] = {
    # ── Common ────────────────────────────────────────────────────────────
    "lang_label":           {"en": "Language", "ko": "언어"},
    "disclaimer": {
        "en": (
            "**Disclaimer:** This dashboard is for informational and educational purposes only. "
            "It does not constitute investment advice. Past performance is not indicative of "
            "future results. Always consult a qualified financial advisor before making "
            "investment decisions."
        ),
        "ko": (
            "**면책 조항:** 이 대시보드는 정보 제공 및 교육 목적으로만 제공됩니다. "
            "투자 조언이 아니며, 과거 성과가 미래 결과를 보장하지 않습니다. "
            "투자 결정 전 반드시 공인 재무 상담사와 상의하세요."
        ),
    },
    "na":                   {"en": "N/A", "ko": "N/A"},
    "select_asset":         {"en": "Select Asset", "ko": "자산 선택"},
    "no_data":              {"en": "No data available.", "ko": "데이터가 없습니다."},
    "no_assets_db":         {"en": "No assets in database.", "ko": "데이터베이스에 자산이 없습니다."},
    "run_collection":       {"en": "Run data collection first.", "ko": "먼저 데이터 수집을 실행하세요."},
    # Asset types
    "at_stock":             {"en": "Stocks", "ko": "주식"},
    "at_bond":              {"en": "Bonds", "ko": "채권"},
    "at_commodity":         {"en": "Commodities", "ko": "원자재"},
    "at_crypto":            {"en": "Crypto", "ko": "암호화폐"},
    "at_fx":                {"en": "FX", "ko": "외환"},
    "at_cash":              {"en": "Cash", "ko": "현금"},
    # ── Sidebar / data refresh ────────────────────────────────────────────
    "sidebar_settings":     {"en": "Settings", "ko": "설정"},
    "data_refresh":         {"en": "Data Refresh", "ko": "데이터 갱신"},
    "last_update":          {"en": "Last data update", "ko": "최근 데이터 시점"},
    "refresh_now":          {"en": "Refresh Data Now", "ko": "지금 데이터 갱신"},
    "refreshing":           {"en": "Collecting market data...", "ko": "시장 데이터 수집 중..."},
    "refresh_done":         {"en": "Data refreshed!", "ko": "데이터 갱신 완료!"},
    "refresh_fail":         {"en": "Refresh failed. Check logs.", "ko": "갱신 실패. 로그를 확인하세요."},
    "auto_refresh":         {"en": "Auto refresh (min)", "ko": "자동 갱신 (분)"},
    "auto_off":             {"en": "Off", "ko": "끄기"},
    # ── Home page ─────────────────────────────────────────────────────────
    "home_title":           {"en": "Market Overview", "ko": "시장 현황"},
    "home_caption":         {"en": "Real-time market snapshot across all tracked asset classes",
                             "ko": "추적 중인 전체 자산 클래스의 시장 스냅샷"},
    "30d_change":           {"en": "30-Day Price Change", "ko": "30일 가격 변동률"},
    "change_pct":           {"en": "Change %", "ko": "변동률 %"},
    "rsi_alerts":           {"en": "RSI Alerts", "ko": "RSI 경보"},
    "overbought":           {"en": "Overbought (RSI >= 70)", "ko": "과매수 (RSI >= 70)"},
    "oversold":             {"en": "Oversold (RSI <= 30)", "ko": "과매도 (RSI <= 30)"},
    "no_overbought":        {"en": "No overbought assets.", "ko": "과매수 자산 없음"},
    "no_oversold":          {"en": "No oversold assets.", "ko": "과매도 자산 없음"},
    "no_rsi_data":          {"en": "No RSI alert data available.", "ko": "RSI 경보 데이터 없음"},
    "yield_curve":          {"en": "Yield Curve Snapshot", "ko": "수익률 곡선 스냅샷"},
    "yield_inverted":       {"en": "Yield curve is **INVERTED** (3m > 10y)", "ko": "수익률 곡선 **역전** (3개월 > 10년)"},
    "yield_normal":         {"en": "Yield curve is **NORMAL** (10y > 3m)", "ko": "수익률 곡선 **정상** (10년 > 3개월)"},
    "no_yield":             {"en": "No yield data available. Run data collection first.",
                             "ko": "수익률 데이터 없음. 먼저 데이터 수집을 실행하세요."},
    "btc_fear":             {"en": "BTC Fear / Greed Proxy", "ko": "BTC 공포/탐욕 지수"},
    "btc_no_data":          {"en": "BTC data not available.", "ko": "BTC 데이터 없음"},
    "yield_pct":            {"en": "Yield %", "ko": "수익률 %"},
    "maturity":             {"en": "Maturity", "ko": "만기"},
    "no_price_change":      {"en": "No price change data available.", "ko": "가격 변동 데이터 없음"},
    # column headers
    "col_ticker":           {"en": "Ticker", "ko": "티커"},
    "col_name":             {"en": "Name", "ko": "종목명"},
    "col_price":            {"en": "Price", "ko": "가격"},
    "col_date":             {"en": "Date", "ko": "날짜"},
    "col_type":             {"en": "Type", "ko": "유형"},
    # ── Portfolio page ────────────────────────────────────────────────────
    "portfolio_title":      {"en": "Portfolio Allocation", "ko": "포트폴리오 배분"},
    "risk_profile":         {"en": "Risk Profile", "ko": "위험 성향"},
    "rp_conservative":      {"en": "Conservative", "ko": "보수적"},
    "rp_moderate":          {"en": "Moderate", "ko": "중립적"},
    "rp_aggressive":        {"en": "Aggressive", "ko": "공격적"},
    "computing_alloc":      {"en": "Computing allocation...", "ko": "배분 계산 중..."},
    "recommended_alloc":    {"en": "Recommended Allocation", "ko": "추천 배분"},
    "asset_scores":         {"en": "Asset Type Scores", "ko": "자산유형별 점수"},
    "no_scores":            {"en": "No score data available.", "ko": "점수 데이터 없음"},
    "rationale":            {"en": "Rationale", "ko": "근거"},
    "save_report":          {"en": "Save Report", "ko": "보고서 저장"},
    "report_saved":         {"en": "Report saved", "ko": "보고서 저장 완료"},
    "score_axis":           {"en": "Score (-1 to +1)", "ko": "점수 (-1 ~ +1)"},
    # ── Risk page ─────────────────────────────────────────────────────────
    "risk_title":           {"en": "Risk Assessment", "ko": "리스크 평가"},
    "overall_risk":         {"en": "Overall Market Risk", "ko": "전체 시장 리스크"},
    "market_risk":          {"en": "Market Risk", "ko": "시장 리스크"},
    "no_risk_data":         {"en": "Insufficient data to compute market risk.",
                             "ko": "시장 리스크를 계산하기에 데이터가 부족합니다."},
    "risk_by_type":         {"en": "Risk by Asset Type", "ko": "자산유형별 리스크"},
    "avg_risk_score":       {"en": "Avg Risk Score", "ko": "평균 리스크 점수"},
    "risk_level":           {"en": "Risk Level", "ko": "리스크 수준"},
    "num_assets":           {"en": "# Assets", "ko": "자산 수"},
    "no_type_risk":         {"en": "No asset-type risk data.", "ko": "자산유형 리스크 데이터 없음"},
    "top5_risk":            {"en": "Top 5 High-Risk Assets", "ko": "고위험 자산 TOP 5"},
    "no_high_risk":         {"en": "No high-risk assets detected.", "ko": "고위험 자산이 감지되지 않았습니다."},
    "individual_risk":      {"en": "Individual Asset Risk Detail", "ko": "개별 자산 리스크 상세"},
    "assessing_risk":       {"en": "Assessing market risk...", "ko": "시장 리스크 평가 중..."},
    "assessing_asset":      {"en": "Assessing asset risk...", "ko": "자산 리스크 평가 중..."},
    "risk_score":           {"en": "Risk Score", "ko": "리스크 점수"},
    "vol_ann":              {"en": "Volatility (ann.)", "ko": "변동성 (연율)"},
    "max_drawdown":         {"en": "Max Drawdown", "ko": "최대 낙폭"},
    "dd_period":            {"en": "Drawdown period", "ko": "낙폭 기간"},
    "asset_not_found":      {"en": "Asset not found in database.", "ko": "데이터베이스에서 자산을 찾을 수 없습니다."},
    # ── Trends page ───────────────────────────────────────────────────────
    "trends_title":         {"en": "Trends & Technical Analysis", "ko": "추세 & 기술적 분석"},
    "trend_map":            {"en": "Trend Map", "ko": "추세 맵"},
    "col_trend":            {"en": "Trend", "ko": "추세"},
    "no_trend_data":        {"en": "No trend data available. Run data collection with --indicators.",
                             "ko": "추세 데이터 없음. --indicators 옵션으로 데이터를 수집하세요."},
    "recent_signals":       {"en": "Recent Signal Events", "ko": "최근 시그널 이벤트"},
    "scanning_signals":     {"en": "Scanning for signals...", "ko": "시그널 탐지 중..."},
    "col_signal":           {"en": "Signal", "ko": "시그널"},
    "col_desc":             {"en": "Description", "ko": "설명"},
    "no_signals":           {"en": "No recent signal events detected.", "ko": "최근 시그널 이벤트 없음"},
    "tech_chart":           {"en": "Technical Chart", "ko": "기술적 차트"},
    "not_enough_data":      {"en": "Not enough price data for chart.", "ko": "차트를 위한 가격 데이터 부족"},
    # ── Sentiment page ────────────────────────────────────────────────────
    "sentiment_title":      {"en": "Sentiment & Butterfly Effect", "ko": "감성분석 & 나비효과"},
    "theme_matrix":         {"en": "Theme Sentiment Matrix", "ko": "테마별 감성 매트릭스"},
    "lookback_days":        {"en": "Lookback (days)", "ko": "조회 기간 (일)"},
    "computing_sent":       {"en": "Computing sentiment matrix...", "ko": "감성 매트릭스 계산 중..."},
    "avg_sentiment":        {"en": "Avg Sentiment", "ko": "평균 감성"},
    "avg_impact":           {"en": "Avg Impact", "ko": "평균 영향도"},
    "no_sentiment":         {"en": "No sentiment data available. Process some news data first.",
                             "ko": "감성 데이터 없음. 뉴스 데이터를 먼저 처리하세요."},
    "divergence_alerts":    {"en": "Theme Divergence Alerts", "ko": "테마 괴리 경보"},
    "detecting_div":        {"en": "Detecting divergences...", "ko": "괴리 탐지 중..."},
    "no_divergence":        {"en": "No significant theme divergences detected.",
                             "ko": "유의미한 테마 괴리가 감지되지 않았습니다."},
    "butterfly_chains":     {"en": "Active Butterfly Chains", "ko": "활성 나비효과 체인"},
    "no_chains":            {"en": "No butterfly chains recorded.", "ko": "기록된 나비효과 체인 없음"},
    "active_signals":       {"en": "Active Investment Signals", "ko": "활성 투자 시그널"},
    "no_active_signals":    {"en": "No active signals.", "ko": "활성 시그널 없음"},
    "col_asset":            {"en": "Asset", "ko": "자산"},
    "col_source":           {"en": "Source", "ko": "소스"},
    "col_strength":         {"en": "Strength", "ko": "강도"},
    "col_rationale":        {"en": "Rationale", "ko": "근거"},
    "col_valid_until":      {"en": "Valid Until", "ko": "유효 기간"},
    "market_wide":          {"en": "Market-wide", "ko": "시장 전체"},
    "open":                 {"en": "Open", "ko": "무기한"},
    "trigger":              {"en": "Trigger", "ko": "트리거"},
    "final_impact":         {"en": "Final Impact", "ko": "최종 영향"},
    "confidence":           {"en": "Confidence", "ko": "신뢰도"},
    "col_theme":            {"en": "Theme", "ko": "테마"},
    "col_sentiment":        {"en": "Sentiment", "ko": "감성"},
    "col_impact":           {"en": "Impact", "ko": "영향도"},
    "col_count":            {"en": "Count", "ko": "건수"},
    "items":                {"en": "Items", "ko": "건"},
    "bullish":              {"en": "Bullish", "ko": "강세"},
    "bearish":              {"en": "Bearish", "ko": "약세"},
    # ── Report page ──────────────────────────────────────────────────────
    "report_title":         {"en": "Advisory Report", "ko": "투자 자문 보고서"},
    "no_reports":           {"en": "No advisory reports saved yet. Generate one from the Portfolio page.",
                             "ko": "저장된 자문 보고서가 없습니다. 포트폴리오 페이지에서 생성하세요."},
    "select_report":        {"en": "Select Report", "ko": "보고서 선택"},
    "executive_summary":    {"en": "Executive Summary", "ko": "요약"},
    "no_summary":           {"en": "No executive summary available.", "ko": "요약 정보 없음"},
    "report_market_overview": {"en": "Market Overview", "ko": "시장 현황"},
    "asset_price_table":    {"en": "All Assets — Price & RSI", "ko": "전체 자산 — 가격 & RSI"},
    "30d_chg":              {"en": "30D Chg", "ko": "30일 변동"},
    "report_allocation":    {"en": "Portfolio Allocation", "ko": "포트폴리오 배분"},
    "weight_pct":           {"en": "Weight %", "ko": "비중 %"},
    "col_score":            {"en": "Score", "ko": "점수"},
    "no_allocation":        {"en": "No allocation data in this report.", "ko": "이 보고서에 배분 데이터 없음"},
    "report_risk":          {"en": "Risk Assessment", "ko": "리스크 평가"},
    "report_signals":       {"en": "Signals & Butterfly Chains", "ko": "시그널 & 나비효과 체인"},
    "report_trends":        {"en": "Trend Overview", "ko": "추세 현황"},
    "uptrend_assets":       {"en": "Uptrend", "ko": "상승 추세"},
    "downtrend_assets":     {"en": "Downtrend", "ko": "하락 추세"},
    "report_comparison":    {"en": "Report History Comparison", "ko": "보고서 이력 비교"},
    # ── Asset detail page ─────────────────────────────────────────────────
    "detail_title":         {"en": "Asset Detail \u2014 360\u00b0 View", "ko": "자산 상세 \u2014 360\u00b0 뷰"},
    "loading_360":          {"en": "Loading 360\u00b0 view", "ko": "360\u00b0 뷰 로딩 중"},
    "no_price_data":        {"en": "No price data available for this asset.", "ko": "이 자산의 가격 데이터 없음"},
    "active_signals_asset": {"en": "Active Signals", "ko": "활성 시그널"},
    "no_signals_asset":     {"en": "No active signals for this asset.", "ko": "이 자산의 활성 시그널 없음"},
    "related_news":         {"en": "Related News", "ko": "관련 뉴스"},
    "no_news":              {"en": "No related news for this asset.", "ko": "이 자산의 관련 뉴스 없음"},
}


def get_lang() -> str:
    """Return the current language code from session state."""
    return st.session_state.get("lang", "en")


def T(key: str) -> str:
    """Translate a key to the current language."""
    lang = get_lang()
    entry = _TRANSLATIONS.get(key)
    if entry is None:
        return key
    return entry.get(lang, entry.get("en", key))


# ── Colour helpers ────────────────────────────────────────────────────────────

_RISK_COLORS = {
    "very_low": "#22c55e",
    "low": "#86efac",
    "moderate": "#facc15",
    "high": "#f97316",
    "very_high": "#ef4444",
    "unknown": "#94a3b8",
}

_TREND_COLORS = {
    "strong_uptrend": "#16a34a",
    "uptrend": "#4ade80",
    "sideways": "#facc15",
    "downtrend": "#fb923c",
    "strong_downtrend": "#dc2626",
    "unknown": "#94a3b8",
}

_SIGNAL_EMOJI = {
    "buy": "\U0001f7e2",
    "sell": "\U0001f534",
    "hold": "\U0001f7e1",
    "overweight": "\U0001f7e2",
    "underweight": "\U0001f534",
}


def risk_color(level: str) -> str:
    return _RISK_COLORS.get(level, "#94a3b8")


def trend_color(trend: str) -> str:
    return _TREND_COLORS.get(trend, "#94a3b8")


def sentiment_color(score: float | None) -> str:
    if score is None:
        return "#94a3b8"
    if score >= 0.2:
        return "#16a34a"
    if score >= 0.05:
        return "#4ade80"
    if score >= -0.05:
        return "#facc15"
    if score >= -0.2:
        return "#fb923c"
    return "#dc2626"


def signal_emoji(signal_type: str) -> str:
    return _SIGNAL_EMOJI.get(signal_type, "\u26aa")


# ── Formatting ────────────────────────────────────────────────────────────────

def fmt_pct(val: float | None, decimals: int = 2) -> str:
    if val is None:
        return "N/A"
    return f"{val:+.{decimals}f}%"


def fmt_price(val: float | None) -> str:
    if val is None:
        return "N/A"
    if abs(val) >= 1_000:
        return f"${val:,.2f}"
    if abs(val) >= 1:
        return f"${val:.2f}"
    return f"${val:.4f}"


def fmt_number(val: float | None, decimals: int = 2) -> str:
    if val is None:
        return "N/A"
    return f"{val:.{decimals}f}"


# ── Asset helpers ─────────────────────────────────────────────────────────────

def all_tickers() -> list[str]:
    """Return sorted list of all active asset tickers."""
    assets = get_db().get_all_assets()
    return sorted(a["ticker"] for a in assets)


def asset_type_label(atype: str) -> str:
    key = f"at_{atype}"
    return T(key) if key in _TRANSLATIONS else atype.title()


# ── Sidebar setup (shared across all pages) ──────────────────────────────────

def render_sidebar():
    """Render common sidebar controls: language toggle + data refresh."""
    with st.sidebar:
        st.header(T("sidebar_settings"))

        # ── Language toggle ───────────────────────────────────────────────
        lang_options = {"English": "en", "한국어": "ko"}
        current = get_lang()
        current_label = next(k for k, v in lang_options.items() if v == current)
        selected_label = st.selectbox(
            T("lang_label"),
            list(lang_options.keys()),
            index=list(lang_options.keys()).index(current_label),
            key="lang_select",
        )
        new_lang = lang_options[selected_label]
        if new_lang != current:
            st.session_state["lang"] = new_lang
            st.rerun()

        st.divider()

        # ── Data refresh ──────────────────────────────────────────────────
        st.subheader(T("data_refresh"))

        # Show last data timestamp
        db = get_db()
        rows = db.execute_readonly(
            "SELECT MAX(date) as last_date FROM market_data"
        )
        last_date = rows[0]["last_date"] if rows and rows[0]["last_date"] else "N/A"
        st.caption(f"{T('last_update')}: **{last_date}**")

        # Manual refresh button
        if st.button(T("refresh_now"), use_container_width=True):
            with st.spinner(T("refreshing")):
                result = subprocess.run(
                    [sys.executable, "scripts/collect_market_data.py",
                     "--days", "30", "--indicators"],
                    capture_output=True, text=True,
                    cwd=str(_PROJECT_ROOT),
                    timeout=300,
                )
            if result.returncode == 0:
                st.success(T("refresh_done"))
                st.cache_resource.clear()
                st.rerun()
            else:
                st.error(T("refresh_fail"))
                with st.expander("Log"):
                    st.code(result.stderr or result.stdout)

        # Auto-refresh interval
        auto_options = {T("auto_off"): 0, "5": 5, "15": 15, "30": 30, "60": 60}
        auto_label = st.selectbox(
            T("auto_refresh"),
            list(auto_options.keys()),
            index=0,
            key="auto_refresh_select",
        )
        auto_min = auto_options[auto_label]
        if auto_min > 0:
            st.caption(f"Page will rerun every {auto_min} min")
            # Use st.empty + experimental_rerun via fragment isn't available,
            # but we can use st's built-in autorefresh via query param workaround:
            # Simplest: use streamlit-autorefresh if available, else just note it.
            try:
                from streamlit_autorefresh import st_autorefresh
                st_autorefresh(interval=auto_min * 60 * 1000, key="auto_refresh")
            except ImportError:
                st.info("Install `streamlit-autorefresh` for auto-refresh support.")


# ── Deprecated constant (kept for backward compat) ───────────────────────────

DISCLAIMER = _TRANSLATIONS["disclaimer"]["en"]
