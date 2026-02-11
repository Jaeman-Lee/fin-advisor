"""Sentiment & Butterfly Effect page."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
import plotly.graph_objects as go

from dashboard.components.helpers import (
    get_db, get_queries, sentiment_color, signal_emoji,
    fmt_number, T, render_sidebar,
)
from src.analysis.cross_theme import (
    compute_theme_sentiment_matrix,
    detect_theme_divergences,
)

st.set_page_config(page_title="Sentiment & Butterfly Effect", page_icon="\U0001f9e0", layout="wide")
render_sidebar()
st.title(f"\U0001f9e0 {T('sentiment_title')}")

db = get_db()
q = get_queries()

# ── Theme sentiment heatmap ───────────────────────────────────────────────────
st.subheader(T("theme_matrix"))

days = st.slider(T("lookback_days"), 7, 90, 30)

with st.spinner(T("computing_sent")):
    matrix = compute_theme_sentiment_matrix(db, days=days)

if matrix:
    categories = list(matrix.keys())
    sentiments = [matrix[c]["avg_sentiment"] for c in categories]
    impacts = [matrix[c]["avg_impact"] for c in categories]

    fig = go.Figure(go.Heatmap(
        z=[sentiments, impacts],
        x=categories,
        y=[T("avg_sentiment"), T("avg_impact")],
        colorscale="RdYlGn", zmid=0,
        text=[[fmt_number(s, 3) for s in sentiments],
              [fmt_number(i, 3) for i in impacts]],
        texttemplate="%{text}",
        hovertemplate="Category: %{x}<br>Metric: %{y}<br>Value: %{z:.3f}<extra></extra>",
    ))
    fig.update_layout(height=250, margin=dict(t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

    for cat in categories:
        data = matrix[cat]
        themes = data.get("themes", [])
        if themes:
            with st.expander(
                f"{cat.title()} — {T('col_sentiment')}: {data['avg_sentiment']:+.3f} | "
                f"{T('items')}: {data['total_items']} | "
                f"{T('bullish')}: {data['bullish_count']} / {T('bearish')}: {data['bearish_count']}"
            ):
                rows = []
                for t in themes:
                    rows.append({
                        T("col_theme"): t.get("name", ""),
                        T("col_sentiment"): fmt_number(t.get("sentiment"), 3),
                        T("col_impact"): fmt_number(t.get("impact"), 3),
                        T("col_count"): t.get("count", 0),
                    })
                st.dataframe(rows, use_container_width=True, hide_index=True)
else:
    st.info(T("no_sentiment"))

st.divider()

# ── Theme divergences ─────────────────────────────────────────────────────────
st.subheader(T("divergence_alerts"))

with st.spinner(T("detecting_div")):
    divergences = detect_theme_divergences(db, days=days)

if divergences:
    for d in divergences:
        st.warning(
            f"**{d['theme_a'].title()} vs {d['theme_b'].title()}** — "
            f"Divergence: {d['divergence_magnitude']:.3f}\n\n"
            f"{d.get('interpretation', '')}"
        )
else:
    st.success(T("no_divergence"))

st.divider()

# ── Butterfly chains ──────────────────────────────────────────────────────────
st.subheader(T("butterfly_chains"))

chains = q.butterfly_chains_active()
if chains:
    for chain in chains:
        conf = chain.get("confidence", 0)
        with st.expander(f"{chain.get('name', 'Chain')} — {T('confidence')}: {conf:.0%}"):
            st.markdown(f"**{T('trigger')}:** {chain.get('trigger_event', 'N/A')}")
            st.markdown(f"**{T('final_impact')}:** {chain.get('final_impact', 'N/A')}")
            detail = chain.get("chain_detail", "")
            if detail:
                for link in detail.split(" | "):
                    st.markdown(f"  \u2192 {link}")
else:
    st.info(T("no_chains"))

st.divider()

# ── Active signals ────────────────────────────────────────────────────────────
st.subheader(T("active_signals"))

signals = q.active_signals_summary()
if signals:
    display = []
    for s in signals:
        emoji = signal_emoji(s.get("signal_type", ""))
        display.append({
            T("col_signal"): f"{emoji} {s.get('signal_type', '').title()}",
            T("col_asset"): s.get("ticker") or s.get("asset_name") or T("market_wide"),
            T("col_type"): s.get("asset_type", ""),
            T("col_source"): s.get("source_type", ""),
            T("col_strength"): fmt_number(s.get("strength"), 2),
            T("col_rationale"): (s.get("rationale") or "")[:80],
            T("col_valid_until"): s.get("valid_until") or T("open"),
        })
    st.dataframe(display, use_container_width=True, hide_index=True)
else:
    st.info(T("no_active_signals"))

st.caption(T("disclaimer"))
