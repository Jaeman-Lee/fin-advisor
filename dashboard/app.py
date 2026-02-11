"""Investment Advisory Dashboard — Home (Market Overview)."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
import plotly.graph_objects as go

from dashboard.components.helpers import (
    get_db, get_queries, fmt_pct, fmt_price, fmt_number,
    asset_type_label, risk_color, T, render_sidebar,
)
from src.collection.macro_data import get_yield_curve_snapshot, is_yield_curve_inverted
from src.collection.crypto_data import get_btc_fear_indicator

st.set_page_config(
    page_title="Investment Advisory Dashboard",
    page_icon="\U0001f4c8",
    layout="wide",
)

render_sidebar()

st.title(f"\U0001f4c8 {T('home_title')}")
st.caption(T("home_caption"))

db = get_db()
q = get_queries()

# ── Top metric cards ──────────────────────────────────────────────────────────
HEADLINE_TICKERS = {
    "^GSPC": "S&P 500",
    "BTC-USD": "Bitcoin",
    "GC=F": "Gold",
    "^TNX": "10Y Yield",
    "DX-Y.NYB": "Dollar (DXY)",
}

price_changes = {r["ticker"]: r for r in q.price_change(days=30)}
latest_all = {r["ticker"]: r for r in q.latest_prices()}

cols = st.columns(len(HEADLINE_TICKERS))
for col, (ticker, label) in zip(cols, HEADLINE_TICKERS.items()):
    row = latest_all.get(ticker, {})
    change_row = price_changes.get(ticker, {})
    price = row.get("close")
    change = change_row.get("change_pct")
    with col:
        st.metric(
            label=label,
            value=fmt_price(price) if price else "N/A",
            delta=fmt_pct(change) if change is not None else None,
        )

st.divider()

# ── Asset-type tabs ───────────────────────────────────────────────────────────
asset_types = ["stock", "bond", "commodity", "crypto", "fx"]
tabs = st.tabs([asset_type_label(at) for at in asset_types])

for tab, atype in zip(tabs, asset_types):
    with tab:
        rows = q.latest_prices(asset_type=atype)
        if not rows:
            st.info(f"{asset_type_label(atype)} — {T('no_data')}")
            continue
        display = []
        for r in rows:
            display.append({
                T("col_ticker"): r["ticker"],
                T("col_name"): r.get("name", ""),
                T("col_price"): fmt_price(r.get("close")),
                "RSI(14)": fmt_number(r.get("rsi_14"), 1),
                "SMA50": fmt_price(r.get("sma_50")),
                "SMA200": fmt_price(r.get("sma_200")),
                T("col_date"): r.get("date", ""),
            })
        st.dataframe(display, use_container_width=True, hide_index=True)

st.divider()

# ── 30-day change bar chart ───────────────────────────────────────────────────
st.subheader(T("30d_change"))

changes = q.price_change(days=30)
if changes:
    tickers = [r["ticker"] for r in changes if r.get("change_pct") is not None]
    pcts = [r["change_pct"] for r in changes if r.get("change_pct") is not None]
    colors = ["#16a34a" if p >= 0 else "#dc2626" for p in pcts]

    fig = go.Figure(go.Bar(
        x=tickers, y=pcts, marker_color=colors,
        text=[f"{p:+.1f}%" for p in pcts], textposition="outside",
    ))
    fig.update_layout(yaxis_title=T("change_pct"), height=400, margin=dict(t=20, b=40))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info(T("no_price_change"))

# ── Overbought / Oversold alerts ─────────────────────────────────────────────
st.subheader(T("rsi_alerts"))

ob_os = q.overbought_oversold()
if ob_os:
    col_ob, col_os = st.columns(2)
    overbought = [r for r in ob_os if r.get("rsi_signal") == "overbought"]
    oversold = [r for r in ob_os if r.get("rsi_signal") == "oversold"]

    with col_ob:
        st.markdown(f"**\U0001f534 {T('overbought')}**")
        if overbought:
            for r in overbought:
                st.warning(f"**{r['ticker']}** — RSI {r['rsi_14']:.1f} | {fmt_price(r.get('close'))}")
        else:
            st.success(T("no_overbought"))

    with col_os:
        st.markdown(f"**\U0001f7e2 {T('oversold')}**")
        if oversold:
            for r in oversold:
                st.info(f"**{r['ticker']}** — RSI {r['rsi_14']:.1f} | {fmt_price(r.get('close'))}")
        else:
            st.success(T("no_oversold"))
else:
    st.info(T("no_rsi_data"))

st.divider()

# ── Yield curve ───────────────────────────────────────────────────────────────
st.subheader(T("yield_curve"))

col_yc, col_fear = st.columns(2)

with col_yc:
    yc = get_yield_curve_snapshot(db)
    labels = ["3m", "5y", "10y", "30y"]
    values = [yc.get(l) for l in labels]
    valid = [(l, v) for l, v in zip(labels, values) if v is not None]

    if valid:
        inverted = is_yield_curve_inverted(db)
        if inverted is True:
            st.error(T("yield_inverted"))
        elif inverted is False:
            st.success(T("yield_normal"))

        fig = go.Figure(go.Scatter(
            x=[v[0] for v in valid], y=[v[1] for v in valid],
            mode="lines+markers+text",
            text=[f"{v[1]:.2f}%" for v in valid], textposition="top center",
            marker=dict(size=10), line=dict(width=3),
        ))
        fig.update_layout(
            yaxis_title=T("yield_pct"), xaxis_title=T("maturity"),
            height=350, margin=dict(t=20),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(T("no_yield"))

with col_fear:
    st.markdown(f"**{T('btc_fear')}**")
    fear = get_btc_fear_indicator(db)
    score = fear.get("score")
    label = fear.get("indicator", "Unknown")

    if score is not None:
        fig = go.Figure(go.Indicator(
            mode="gauge+number", value=score,
            title={"text": label},
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
        fig.update_layout(height=350, margin=dict(t=60, b=20))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(T("btc_no_data"))

st.divider()
st.caption(T("disclaimer"))
