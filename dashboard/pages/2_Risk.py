"""Risk Assessment page."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
import plotly.graph_objects as go

from dashboard.components.helpers import (
    get_db, get_queries, risk_color, fmt_pct, fmt_number,
    asset_type_label, all_tickers, T, render_sidebar,
)
from src.analysis.risk_assessor import assess_market_risk, assess_asset_risk

st.set_page_config(page_title="Risk Assessment", page_icon="\u26a0\ufe0f", layout="wide")
render_sidebar()
st.title(f"\u26a0\ufe0f {T('risk_title')}")

db = get_db()

with st.spinner(T("assessing_risk")):
    market_risk = assess_market_risk(db)

overall_score = market_risk.get("risk_score")
overall_level = market_risk.get("overall_risk", "unknown")

# ── Overall risk gauge ────────────────────────────────────────────────────────
st.subheader(T("overall_risk"))

if overall_score is not None:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=overall_score * 100,
        number={"suffix": "%"},
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
    fig.update_layout(height=350, margin=dict(t=60, b=20))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info(T("no_risk_data"))

st.divider()

# ── Risk by asset type ────────────────────────────────────────────────────────
st.subheader(T("risk_by_type"))

risk_by_type = market_risk.get("risk_by_type", {})
if risk_by_type:
    rows = []
    for atype, data in risk_by_type.items():
        level = data.get("risk_level", "unknown")
        rows.append({
            T("col_type"): asset_type_label(atype),
            T("avg_risk_score"): fmt_number(data.get("avg_risk"), 3),
            T("risk_level"): level.replace("_", " ").title(),
            T("num_assets"): data.get("count", 0),
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)
else:
    st.info(T("no_type_risk"))

st.divider()

# ── High-risk TOP 5 ──────────────────────────────────────────────────────────
st.subheader(T("top5_risk"))

high_risk = market_risk.get("high_risk_assets", [])
if high_risk:
    cols = st.columns(min(len(high_risk), 5))
    for col, asset in zip(cols, high_risk[:5]):
        level = asset.get("risk_level", "unknown")
        with col:
            st.markdown(
                f"<div style='border-left: 4px solid {risk_color(level)}; "
                f"padding: 0.5rem 0.75rem; margin-bottom: 0.5rem;'>"
                f"<strong>{asset.get('ticker', '?')}</strong><br>"
                f"{T('risk_score')}: {fmt_number(asset.get('risk_score'), 3)}<br>"
                f"Vol: {fmt_pct(asset.get('volatility_annualized', 0) * 100 if asset.get('volatility_annualized') else None)}<br>"
                f"MDD: {fmt_pct(asset.get('max_drawdown', 0) * 100 if asset.get('max_drawdown') else None)}<br>"
                f"RSI: {fmt_number(asset.get('current_rsi'), 1)}"
                f"</div>",
                unsafe_allow_html=True,
            )
else:
    st.info(T("no_high_risk"))

st.divider()

# ── Individual asset risk ─────────────────────────────────────────────────────
st.subheader(T("individual_risk"))

tickers = all_tickers()
if tickers:
    selected_ticker = st.selectbox(T("select_asset"), tickers)
    if selected_ticker:
        asset_id = db.get_asset_id(selected_ticker)
        if asset_id:
            with st.spinner(T("assessing_asset")):
                asset_risk = assess_asset_risk(db, asset_id)

            a_level = asset_risk.get("risk_level", "unknown")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(T("risk_score"), fmt_number(asset_risk.get("risk_score"), 3))
            c2.metric(T("risk_level"), a_level.replace("_", " ").title())
            c3.metric(
                T("vol_ann"),
                fmt_pct(asset_risk.get("volatility_annualized", 0) * 100
                        if asset_risk.get("volatility_annualized") else None),
            )
            c4.metric(
                T("max_drawdown"),
                fmt_pct(asset_risk.get("max_drawdown", 0) * 100
                        if asset_risk.get("max_drawdown") else None),
            )
            if asset_risk.get("drawdown_peak") and asset_risk.get("drawdown_trough"):
                st.caption(
                    f"{T('dd_period')}: {asset_risk['drawdown_peak']} → {asset_risk['drawdown_trough']}"
                )
        else:
            st.warning(f"{selected_ticker} — {T('asset_not_found')}")
else:
    st.info(T("no_assets_db"))

st.caption(T("disclaimer"))
