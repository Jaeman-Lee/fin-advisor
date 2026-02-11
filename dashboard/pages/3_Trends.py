"""Trends & Technical Analysis page."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from dashboard.components.helpers import (
    get_db, get_queries, trend_color, fmt_price, fmt_number,
    all_tickers, asset_type_label, T, render_sidebar,
)
from src.analysis.trend_detector import get_all_trend_signals

st.set_page_config(page_title="Trends & Technical Analysis", page_icon="\U0001f4c9", layout="wide")
render_sidebar()
st.title(f"\U0001f4c9 {T('trends_title')}")

db = get_db()
q = get_queries()

# ── Trend map table ───────────────────────────────────────────────────────────
st.subheader(T("trend_map"))

trend_data = q.trend_analysis()
if trend_data:
    rows = []
    for r in trend_data:
        trend = r.get("trend", "unknown")
        rows.append({
            T("col_ticker"): r["ticker"],
            T("col_name"): r.get("name", ""),
            T("col_type"): asset_type_label(r.get("asset_type", "")),
            T("col_price"): fmt_price(r.get("close")),
            "SMA20": fmt_price(r.get("sma_20")),
            "SMA50": fmt_price(r.get("sma_50")),
            "SMA200": fmt_price(r.get("sma_200")),
            T("col_trend"): trend.replace("_", " ").title(),
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)
else:
    st.info(T("no_trend_data"))

st.divider()

# ── Signal events ─────────────────────────────────────────────────────────────
st.subheader(T("recent_signals"))

with st.spinner(T("scanning_signals")):
    all_signals = get_all_trend_signals(db)

events: list[dict] = []
for ticker, sigs in all_signals.items():
    for s in sigs:
        if s.get("type") == "current_trend":
            continue
        events.append({"Ticker": ticker, **s})

if events:
    events.sort(key=lambda e: e.get("date", ""), reverse=True)
    display = []
    for e in events[:30]:
        sig_type = e.get("type", "")
        signal = e.get("signal", "")
        emoji = "\U0001f7e2" if signal == "bullish" else "\U0001f534" if signal == "bearish" else "\u26aa"
        display.append({
            T("col_date"): e.get("date", ""),
            T("col_ticker"): e.get("Ticker", ""),
            T("col_signal"): f"{emoji} {sig_type.replace('_', ' ').title()}",
            T("col_desc"): e.get("description", ""),
        })
    st.dataframe(display, use_container_width=True, hide_index=True)
else:
    st.info(T("no_signals"))

st.divider()

# ── Individual asset candlestick chart ────────────────────────────────────────
st.subheader(T("tech_chart"))

tickers = all_tickers()
if tickers:
    selected = st.selectbox(T("select_asset"), tickers, key="trend_asset")
    if selected:
        asset_id = db.get_asset_id(selected)
        if asset_id:
            prices = db.get_market_data(asset_id, limit=120)
            prices = prices[::-1]

            if len(prices) >= 2:
                dates = [p["date"] for p in prices]
                opens = [p.get("open") for p in prices]
                highs = [p.get("high") for p in prices]
                lows = [p.get("low") for p in prices]
                closes = [p.get("close") for p in prices]
                sma20 = [p.get("sma_20") for p in prices]
                sma50 = [p.get("sma_50") for p in prices]
                sma200 = [p.get("sma_200") for p in prices]
                rsi = [p.get("rsi_14") for p in prices]

                fig = make_subplots(
                    rows=2, cols=1, shared_xaxes=True,
                    vertical_spacing=0.08, row_heights=[0.7, 0.3],
                    subplot_titles=[f"{selected} — {T('col_price')} + SMA", "RSI (14)"],
                )

                fig.add_trace(go.Candlestick(
                    x=dates, open=opens, high=highs, low=lows, close=closes, name="OHLC",
                ), row=1, col=1)

                if any(v is not None for v in sma20):
                    fig.add_trace(go.Scatter(
                        x=dates, y=sma20, mode="lines",
                        name="SMA 20", line=dict(width=1, color="#3b82f6"),
                    ), row=1, col=1)
                if any(v is not None for v in sma50):
                    fig.add_trace(go.Scatter(
                        x=dates, y=sma50, mode="lines",
                        name="SMA 50", line=dict(width=1, color="#f59e0b"),
                    ), row=1, col=1)
                if any(v is not None for v in sma200):
                    fig.add_trace(go.Scatter(
                        x=dates, y=sma200, mode="lines",
                        name="SMA 200", line=dict(width=1, color="#ef4444"),
                    ), row=1, col=1)

                if any(v is not None for v in rsi):
                    fig.add_trace(go.Scatter(
                        x=dates, y=rsi, mode="lines",
                        name="RSI", line=dict(width=2, color="#8b5cf6"),
                    ), row=2, col=1)
                    fig.add_hline(y=70, line_dash="dash", line_color="#dc2626",
                                  annotation_text=T("overbought").split("(")[0].strip(), row=2, col=1)
                    fig.add_hline(y=30, line_dash="dash", line_color="#16a34a",
                                  annotation_text=T("oversold").split("(")[0].strip(), row=2, col=1)

                fig.update_layout(height=650, xaxis_rangeslider_visible=False, margin=dict(t=40, b=20))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info(T("not_enough_data"))
        else:
            st.warning(f"{selected} — {T('asset_not_found')}")
else:
    st.info(T("no_assets_db"))

st.caption(T("disclaimer"))
