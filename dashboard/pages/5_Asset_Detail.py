"""Asset Detail — 360-degree view of a single asset."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from dashboard.components.helpers import (
    get_db, get_queries, fmt_price, fmt_number, fmt_pct,
    signal_emoji, sentiment_color, all_tickers, T, render_sidebar,
)

st.set_page_config(page_title="Asset Detail", page_icon="\U0001f50d", layout="wide")
render_sidebar()
st.title(f"\U0001f50d {T('detail_title')}")

db = get_db()
q = get_queries()

tickers = all_tickers()
if not tickers:
    st.info(f"{T('no_assets_db')} {T('run_collection')}")
    st.stop()

selected = st.selectbox(T("select_asset"), tickers)
if not selected:
    st.stop()

with st.spinner(f"{T('loading_360')} {selected}..."):
    view = q.asset_360_view(selected)

if "error" in view:
    st.error(view["error"])
    st.stop()

prices = view.get("recent_prices", [])
signals = view.get("active_signals", [])
news = view.get("recent_news", [])

# ── Price chart (candlestick + SMA + RSI/MACD subplots) ──────────────────────
if prices:
    prices_asc = prices[::-1]
    dates = [p["date"] for p in prices_asc]
    closes = [p.get("close") for p in prices_asc]
    rsi = [p.get("rsi_14") for p in prices_asc]
    macd = [p.get("macd") for p in prices_asc]
    macd_sig = [p.get("macd_signal") for p in prices_asc]

    asset_id = db.get_asset_id(selected)
    full_prices = db.get_market_data(asset_id, limit=30)[::-1] if asset_id else []
    has_ohlc = full_prices and all(
        full_prices[0].get(k) is not None for k in ("open", "high", "low", "close")
    )

    has_macd = any(v is not None for v in macd)
    has_rsi = any(v is not None for v in rsi)
    n_rows = 1 + (1 if has_rsi else 0) + (1 if has_macd else 0)
    heights = [0.5] + [0.25] * (n_rows - 1) if n_rows > 1 else [1.0]
    subtitles = [f"{selected} — {T('col_price')}"]
    if has_rsi:
        subtitles.append("RSI (14)")
    if has_macd:
        subtitles.append("MACD")

    fig = make_subplots(
        rows=n_rows, cols=1, shared_xaxes=True,
        vertical_spacing=0.06, row_heights=heights,
        subplot_titles=subtitles,
    )

    if has_ohlc:
        fp_dates = [p["date"] for p in full_prices]
        fig.add_trace(go.Candlestick(
            x=fp_dates,
            open=[p.get("open") for p in full_prices],
            high=[p.get("high") for p in full_prices],
            low=[p.get("low") for p in full_prices],
            close=[p.get("close") for p in full_prices],
            name="OHLC",
        ), row=1, col=1)
    else:
        fig.add_trace(go.Scatter(
            x=dates, y=closes, mode="lines", name="Close", line=dict(width=2),
        ), row=1, col=1)

    src_dates = [p["date"] for p in full_prices] if has_ohlc else dates
    src_prices = full_prices if has_ohlc else prices_asc
    sma20_src = [p.get("sma_20") for p in src_prices]
    sma50_src = [p.get("sma_50") for p in src_prices]
    sma200_src = [p.get("sma_200") for p in src_prices]
    bb_upper_src = [p.get("bb_upper") for p in src_prices]
    bb_lower_src = [p.get("bb_lower") for p in src_prices]

    if any(v is not None for v in sma20_src):
        fig.add_trace(go.Scatter(
            x=src_dates, y=sma20_src, mode="lines",
            name="SMA 20", line=dict(width=1, color="#3b82f6"),
        ), row=1, col=1)
    if any(v is not None for v in sma50_src):
        fig.add_trace(go.Scatter(
            x=src_dates, y=sma50_src, mode="lines",
            name="SMA 50", line=dict(width=1, color="#f59e0b"),
        ), row=1, col=1)
    if any(v is not None for v in sma200_src):
        fig.add_trace(go.Scatter(
            x=src_dates, y=sma200_src, mode="lines",
            name="SMA 200", line=dict(width=1, color="#ef4444"),
        ), row=1, col=1)
    if any(v is not None for v in bb_upper_src):
        fig.add_trace(go.Scatter(
            x=src_dates, y=bb_upper_src, mode="lines",
            name="BB Upper", line=dict(width=1, dash="dot", color="#94a3b8"),
        ), row=1, col=1)
    if any(v is not None for v in bb_lower_src):
        fig.add_trace(go.Scatter(
            x=src_dates, y=bb_lower_src, mode="lines",
            name="BB Lower", line=dict(width=1, dash="dot", color="#94a3b8"),
        ), row=1, col=1)

    current_row = 2
    if has_rsi:
        fig.add_trace(go.Scatter(
            x=dates, y=rsi, mode="lines",
            name="RSI", line=dict(width=2, color="#8b5cf6"),
        ), row=current_row, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="#dc2626", row=current_row, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="#16a34a", row=current_row, col=1)
        current_row += 1

    if has_macd:
        fig.add_trace(go.Scatter(
            x=dates, y=macd, mode="lines",
            name="MACD", line=dict(width=2, color="#3b82f6"),
        ), row=current_row, col=1)
        if any(v is not None for v in macd_sig):
            fig.add_trace(go.Scatter(
                x=dates, y=macd_sig, mode="lines",
                name="Signal", line=dict(width=1.5, color="#f97316"),
            ), row=current_row, col=1)
        hist = [
            (m - s) if m is not None and s is not None else None
            for m, s in zip(macd, macd_sig)
        ]
        if any(v is not None for v in hist):
            colors = ["#16a34a" if (h or 0) >= 0 else "#dc2626" for h in hist]
            fig.add_trace(go.Bar(
                x=dates, y=hist, name="MACD Hist", marker_color=colors,
            ), row=current_row, col=1)

    fig.update_layout(
        height=200 + 250 * n_rows,
        xaxis_rangeslider_visible=False,
        margin=dict(t=40, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info(T("no_price_data"))

# ── Active signals ────────────────────────────────────────────────────────────
st.subheader(T("active_signals_asset"))

if signals:
    for s in signals:
        emoji = signal_emoji(s.get("signal_type", ""))
        strength = s.get("strength", 0)
        st.markdown(
            f"{emoji} **{s.get('signal_type', '').title()}** "
            f"({T('col_strength')}: {strength:.2f}) — "
            f"*{s.get('source_type', '')}* — "
            f"{s.get('rationale', '')}"
        )
else:
    st.info(T("no_signals_asset"))

st.divider()

# ── Related news ──────────────────────────────────────────────────────────────
st.subheader(T("related_news"))

if news:
    for n in news:
        sent = n.get("sentiment_score")
        color = sentiment_color(sent)
        impact = n.get("impact_score")
        st.markdown(
            f"<div style='border-left: 4px solid {color}; padding: 0.4rem 0.75rem; "
            f"margin-bottom: 0.5rem;'>"
            f"<strong>{n.get('title', 'Untitled')}</strong><br>"
            f"<small>{T('col_sentiment')}: {fmt_number(sent, 3)} | "
            f"{T('col_impact')}: {fmt_number(impact, 3)} | "
            f"{n.get('processed_at', '')}</small><br>"
            f"{n.get('summary', '') or ''}"
            f"</div>",
            unsafe_allow_html=True,
        )
else:
    st.info(T("no_news"))

st.caption(T("disclaimer"))
