"""Portfolio Allocation page."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st
import plotly.graph_objects as go

from dashboard.components.helpers import (
    get_db, fmt_pct, asset_type_label, T, render_sidebar,
)
from src.analysis.allocation_engine import generate_allocation, store_allocation_as_report

st.set_page_config(page_title="Portfolio Allocation", page_icon="\U0001f4ca", layout="wide")
render_sidebar()
st.title(f"\U0001f4ca {T('portfolio_title')}")

db = get_db()

# ── Risk-profile selector ────────────────────────────────────────────────────
risk_map = {
    T("rp_conservative"): "conservative",
    T("rp_moderate"): "moderate",
    T("rp_aggressive"): "aggressive",
}
selected = st.selectbox(T("risk_profile"), list(risk_map.keys()), index=1)
risk_tolerance = risk_map[selected]

with st.spinner(T("computing_alloc")):
    result = generate_allocation(db, risk_tolerance=risk_tolerance)

allocation = result["allocation"]
rationale = result["rationale"]
scores = result.get("scores", {})

# ── Pie chart ─────────────────────────────────────────────────────────────────
col_pie, col_bar = st.columns(2)

with col_pie:
    st.subheader(T("recommended_alloc"))
    labels = [asset_type_label(k) for k in allocation]
    values = list(allocation.values())
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.4, textinfo="label+percent",
        marker=dict(colors=["#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#6b7280"]),
    ))
    fig.update_layout(height=400, margin=dict(t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

# ── Score bar chart ───────────────────────────────────────────────────────────
with col_bar:
    st.subheader(T("asset_scores"))
    if scores:
        types = list(scores.keys())
        score_vals = [scores[t]["score"] for t in types]
        colors = ["#16a34a" if s >= 0 else "#dc2626" for s in score_vals]
        fig = go.Figure(go.Bar(
            x=[asset_type_label(t) for t in types], y=score_vals,
            marker_color=colors, text=[f"{s:+.3f}" for s in score_vals],
            textposition="outside",
        ))
        fig.update_layout(
            yaxis_title=T("score_axis"), yaxis=dict(range=[-1.1, 1.1]),
            height=400, margin=dict(t=20, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(T("no_scores"))

# ── Rationale table ───────────────────────────────────────────────────────────
st.subheader(T("rationale"))
for atype, weight in sorted(allocation.items(), key=lambda x: -x[1]):
    with st.expander(f"{asset_type_label(atype)} — {weight:.1f}%"):
        st.write(rationale.get(atype, ""))
        if atype in scores:
            factors = scores[atype].get("factors", [])
            if factors:
                for f in factors:
                    st.markdown(f"- {f}")

# ── Save report ───────────────────────────────────────────────────────────────
st.divider()
if st.button(T("save_report")):
    report_id = store_allocation_as_report(db, result)
    st.success(f"{T('report_saved')} (ID: {report_id})")

st.caption(T("disclaimer"))
