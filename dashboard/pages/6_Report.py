"""Advisory Report — view stored reports with full analysis context."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import json

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from dashboard.components.helpers import (
    get_db, get_queries, fmt_price, fmt_pct, fmt_number,
    asset_type_label, risk_color, sentiment_color, T, render_sidebar,
)
from src.analysis.risk_assessor import assess_market_risk
from src.collection.macro_data import get_yield_curve_snapshot, is_yield_curve_inverted
from src.collection.crypto_data import get_btc_fear_indicator

st.set_page_config(page_title="Advisory Report", page_icon="\U0001f4cb", layout="wide")
render_sidebar()
st.title(f"\U0001f4cb {T('report_title')}")

db = get_db()
q = get_queries()

# ── Load reports ─────────────────────────────────────────────────────────────
reports = db.execute_readonly(
    "SELECT id, report_type, title, executive_summary, market_overview, "
    "recommendations, risk_assessment, created_at "
    "FROM advisory_reports ORDER BY created_at DESC"
)

if not reports:
    st.info(T("no_reports"))
    st.stop()

# ── Report selector ──────────────────────────────────────────────────────────
report_options = {
    f"#{r['id']} | {r['created_at'][:16]} | {r['title']}": r for r in reports
}
selected_label = st.selectbox(T("select_report"), list(report_options.keys()))
report = report_options[selected_label]

st.divider()

# ── 1. Executive Summary ─────────────────────────────────────────────────────
st.subheader(T("executive_summary"))
summary = report.get("executive_summary") or ""
if summary:
    st.code(summary, language=None)
else:
    st.info(T("no_summary"))

st.divider()

# ── 2. Market Overview (live) ────────────────────────────────────────────────
st.subheader(T("report_market_overview"))

# Headline metrics
HEADLINE_TICKERS = {
    "^GSPC": "S&P 500", "^IXIC": "NASDAQ", "^DJI": "Dow Jones",
    "BTC-USD": "Bitcoin", "GC=F": "Gold", "^TNX": "10Y Yield", "DX-Y.NYB": "DXY",
}
latest_all = {r["ticker"]: r for r in q.latest_prices()}
price_changes = {r["ticker"]: r for r in q.price_change(days=30)}

cols = st.columns(len(HEADLINE_TICKERS))
for col, (ticker, label) in zip(cols, HEADLINE_TICKERS.items()):
    row = latest_all.get(ticker, {})
    change_row = price_changes.get(ticker, {})
    with col:
        st.metric(
            label=label,
            value=fmt_price(row.get("close")) if row.get("close") else "N/A",
            delta=fmt_pct(change_row.get("change_pct")) if change_row.get("change_pct") is not None else None,
        )

# Asset-type summary table
st.markdown(f"**{T('asset_price_table')}**")
all_prices = q.latest_prices()
if all_prices:
    rows_display = []
    for r in all_prices:
        change = price_changes.get(r["ticker"], {})
        rows_display.append({
            T("col_ticker"): r["ticker"],
            T("col_name"): r.get("name", ""),
            T("col_type"): asset_type_label(r.get("asset_type", "")),
            T("col_price"): fmt_price(r.get("close")),
            "RSI(14)": fmt_number(r.get("rsi_14"), 1),
            T("30d_chg"): fmt_pct(change.get("change_pct")) if change.get("change_pct") is not None else "N/A",
        })
    st.dataframe(rows_display, use_container_width=True, hide_index=True)

# RSI alerts
ob_os = q.overbought_oversold()
if ob_os:
    col_ob, col_os = st.columns(2)
    overbought = [r for r in ob_os if r.get("rsi_signal") == "overbought"]
    oversold = [r for r in ob_os if r.get("rsi_signal") == "oversold"]
    with col_ob:
        st.markdown(f"**\U0001f534 {T('overbought')}**")
        for r in overbought:
            st.warning(f"**{r['ticker']}** RSI {r['rsi_14']:.1f}")
    with col_os:
        st.markdown(f"**\U0001f7e2 {T('oversold')}**")
        for r in oversold:
            st.info(f"**{r['ticker']}** RSI {r['rsi_14']:.1f}")

# Macro: yield curve + BTC fear
col_yc, col_btc = st.columns(2)
with col_yc:
    st.markdown(f"**{T('yield_curve')}**")
    yc = get_yield_curve_snapshot(db)
    labels_yc = ["3m", "5y", "10y", "30y"]
    values_yc = [yc.get(l) for l in labels_yc]
    valid_yc = [(l, v) for l, v in zip(labels_yc, values_yc) if v is not None]
    if valid_yc:
        inverted = is_yield_curve_inverted(db)
        if inverted:
            st.error(T("yield_inverted"))
        else:
            st.success(T("yield_normal"))
        fig_yc = go.Figure(go.Scatter(
            x=[v[0] for v in valid_yc], y=[v[1] for v in valid_yc],
            mode="lines+markers+text",
            text=[f"{v[1]:.2f}%" for v in valid_yc], textposition="top center",
            marker=dict(size=10), line=dict(width=3),
        ))
        fig_yc.update_layout(yaxis_title=T("yield_pct"), height=300, margin=dict(t=20))
        st.plotly_chart(fig_yc, use_container_width=True)

with col_btc:
    st.markdown(f"**{T('btc_fear')}**")
    fear = get_btc_fear_indicator(db)
    score = fear.get("score")
    if score is not None:
        fig_f = go.Figure(go.Indicator(
            mode="gauge+number", value=score,
            title={"text": fear.get("indicator", "")},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#1e293b"},
                "steps": [
                    {"range": [0, 25], "color": "#dc2626"},
                    {"range": [25, 40], "color": "#f97316"},
                    {"range": [40, 60], "color": "#facc15"},
                    {"range": [60, 75], "color": "#4ade80"},
                    {"range": [75, 100], "color": "#16a34a"},
                ],
            },
        ))
        fig_f.update_layout(height=300, margin=dict(t=60, b=20))
        st.plotly_chart(fig_f, use_container_width=True)

st.divider()

# ── 3. Portfolio Allocation (from report) ────────────────────────────────────
st.subheader(T("report_allocation"))

rec_raw = report.get("recommendations") or "{}"
try:
    allocation = json.loads(rec_raw) if isinstance(rec_raw, str) else rec_raw
except (json.JSONDecodeError, TypeError):
    allocation = {}

if allocation:
    col_pie, col_table = st.columns(2)

    with col_pie:
        labels = [asset_type_label(k) for k in allocation]
        values = list(allocation.values())
        colors = ["#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#6b7280", "#ec4899"]
        fig_pie = go.Figure(go.Pie(
            labels=labels, values=values, hole=0.4, textinfo="label+percent",
            marker=dict(colors=colors[:len(labels)]),
        ))
        fig_pie.update_layout(height=400, margin=dict(t=20, b=20))
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_table:
        risk_raw = report.get("risk_assessment") or "{}"
        try:
            scores = json.loads(risk_raw) if isinstance(risk_raw, str) else risk_raw
        except (json.JSONDecodeError, TypeError):
            scores = {}

        table_rows = []
        for atype, weight in sorted(allocation.items(), key=lambda x: -x[1]):
            score_info = scores.get(atype, {})
            factors = score_info.get("factors", [])
            table_rows.append({
                T("col_type"): asset_type_label(atype),
                T("weight_pct"): f"{weight:.1f}%",
                T("col_score"): fmt_number(score_info.get("score"), 3) if "score" in score_info else "N/A",
                T("col_rationale"): " | ".join(factors)[:100] if factors else "",
            })
        st.dataframe(table_rows, use_container_width=True, hide_index=True)
else:
    st.info(T("no_allocation"))

st.divider()

# ── 4. Risk Assessment (live) ────────────────────────────────────────────────
st.subheader(T("report_risk"))

with st.spinner(T("assessing_risk")):
    market_risk = assess_market_risk(db)

overall = market_risk.get("risk_score")
overall_level = market_risk.get("overall_risk", "unknown")

col_gauge, col_types = st.columns(2)

with col_gauge:
    if overall is not None:
        fig_r = go.Figure(go.Indicator(
            mode="gauge+number", value=overall * 100, number={"suffix": "%"},
            title={"text": f"{T('market_risk')} — {overall_level.replace('_', ' ').title()}"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": risk_color(overall_level)},
                "steps": [
                    {"range": [0, 20], "color": "#dcfce7"},
                    {"range": [20, 40], "color": "#fef9c3"},
                    {"range": [40, 60], "color": "#fef3c7"},
                    {"range": [60, 80], "color": "#fed7aa"},
                    {"range": [80, 100], "color": "#fecaca"},
                ],
            },
        ))
        fig_r.update_layout(height=350, margin=dict(t=60, b=20))
        st.plotly_chart(fig_r, use_container_width=True)

with col_types:
    risk_by_type = market_risk.get("risk_by_type", {})
    if risk_by_type:
        type_rows = []
        for atype, data in risk_by_type.items():
            type_rows.append({
                T("col_type"): asset_type_label(atype),
                T("risk_level"): data.get("risk_level", "").replace("_", " ").title(),
                T("avg_risk_score"): fmt_number(data.get("avg_risk"), 3),
                T("num_assets"): data.get("count", 0),
            })
        st.dataframe(type_rows, use_container_width=True, hide_index=True)

    # High-risk top 5
    high_risk = market_risk.get("high_risk_assets", [])
    if high_risk:
        st.markdown(f"**{T('top5_risk')}**")
        hr_rows = []
        for a in high_risk[:5]:
            hr_rows.append({
                T("col_ticker"): a.get("ticker", "?"),
                T("risk_level"): a.get("risk_level", "").replace("_", " ").title(),
                T("vol_ann"): fmt_pct(
                    a.get("volatility_annualized", 0) * 100
                    if a.get("volatility_annualized") else None
                ),
                T("max_drawdown"): fmt_pct(
                    a.get("max_drawdown", 0) * 100
                    if a.get("max_drawdown") else None
                ),
            })
        st.dataframe(hr_rows, use_container_width=True, hide_index=True)

st.divider()

# ── 5. Butterfly Chains & Sentiment ──────────────────────────────────────────
st.subheader(T("report_signals"))

col_chains, col_sent = st.columns(2)

with col_chains:
    st.markdown(f"**{T('butterfly_chains')}**")
    chains = q.butterfly_chains_active(min_confidence=0.05)
    if chains:
        for chain in chains:
            conf = chain.get("confidence", 0)
            trigger = chain.get("trigger_event", "N/A")
            impact = chain.get("final_impact", "N/A")
            detail = chain.get("chain_detail", "")
            with st.expander(f"{trigger} \u2192 {impact} ({conf:.0%})"):
                if detail:
                    for link in detail.split(" | "):
                        st.markdown(f"\u2192 {link}")
    else:
        st.info(T("no_chains"))

with col_sent:
    st.markdown(f"**{T('active_signals')}**")
    signals = q.active_signals_summary()
    if signals:
        sig_rows = []
        for s in signals:
            sig_rows.append({
                T("col_signal"): s.get("signal_type", "").title(),
                T("col_asset"): s.get("ticker") or T("market_wide"),
                T("col_strength"): fmt_number(s.get("strength"), 2),
                T("col_rationale"): (s.get("rationale") or "")[:60],
            })
        st.dataframe(sig_rows, use_container_width=True, hide_index=True)
    else:
        st.info(T("no_active_signals"))

# ── 6. Trend overview chart ──────────────────────────────────────────────────
st.divider()
st.subheader(T("report_trends"))

trend_data = q.trend_analysis()
if trend_data:
    uptrend = [t for t in trend_data if "up" in t.get("trend", "")]
    downtrend = [t for t in trend_data if "down" in t.get("trend", "")]

    col_up, col_down = st.columns(2)
    with col_up:
        st.markdown(f"**\U0001f7e2 {T('uptrend_assets')}** ({len(uptrend)})")
        for t in uptrend:
            chg = price_changes.get(t["ticker"], {}).get("change_pct")
            chg_str = f" ({chg:+.1f}%)" if chg is not None else ""
            st.markdown(f"- **{t['ticker']}** {fmt_price(t.get('close'))}{chg_str}")
    with col_down:
        st.markdown(f"**\U0001f534 {T('downtrend_assets')}** ({len(downtrend)})")
        for t in downtrend:
            chg = price_changes.get(t["ticker"], {}).get("change_pct")
            chg_str = f" ({chg:+.1f}%)" if chg is not None else ""
            st.markdown(f"- **{t['ticker']}** {fmt_price(t.get('close'))}{chg_str}")

# 30-day change bar chart
changes_list = q.price_change(days=30)
valid_changes = [r for r in changes_list if r.get("change_pct") is not None]
if valid_changes:
    tickers = [r["ticker"] for r in valid_changes]
    pcts = [r["change_pct"] for r in valid_changes]
    colors = ["#16a34a" if p >= 0 else "#dc2626" for p in pcts]

    fig_bar = go.Figure(go.Bar(
        x=tickers, y=pcts, marker_color=colors,
        text=[f"{p:+.1f}%" for p in pcts], textposition="outside",
    ))
    fig_bar.update_layout(yaxis_title=T("change_pct"), height=400, margin=dict(t=20, b=40))
    st.plotly_chart(fig_bar, use_container_width=True)

st.divider()

# ── Report comparison (if multiple reports exist) ────────────────────────────
if len(reports) >= 2:
    st.subheader(T("report_comparison"))
    comparison_rows = []
    for r in reports[:5]:
        rec = r.get("recommendations") or "{}"
        try:
            alloc = json.loads(rec) if isinstance(rec, str) else rec
        except (json.JSONDecodeError, TypeError):
            alloc = {}
        row = {T("col_date"): r["created_at"][:16], "ID": r["id"]}
        for atype in ["stock", "bond", "commodity", "crypto", "cash"]:
            row[asset_type_label(atype)] = f"{alloc.get(atype, 0):.1f}%"
        comparison_rows.append(row)
    st.dataframe(comparison_rows, use_container_width=True, hide_index=True)

st.divider()
st.caption(T("disclaimer"))
