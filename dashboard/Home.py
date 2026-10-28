"""
dashboard/Home.py: Executive overview, the first page anyone sees.

Run the whole dashboard with:   uv run run.py dashboard
(or: uv run streamlit run dashboard/Home.py)

Streamlit turns this script into a web page. Every st.something() call adds an
element to the page, top to bottom. Files in dashboard/pages/ become the other
pages in the sidebar, ordered by the number at the start of their names.
"""

import plotly.graph_objects as go
import streamlit as st

from data import SEGMENT_COLORS, SEGMENTS, footer, money, query

st.set_page_config(page_title="ChurnLens", page_icon="📉", layout="wide")

st.title("ChurnLens: executive overview")
st.caption("Enterprise B2B telemetry and churn intelligence. How much revenue do we have, "
           "are we keeping it, and how much is at risk right now?")

# --- KPI tiles -------------------------------------------------------------------
bridge = query("SELECT * FROM mart_arr_bridge ORDER BY month_start")
retention = query("SELECT * FROM metric_retention_12m ORDER BY month_start")
health_now = query("SELECT risk_tier, arr, arr_at_risk FROM fact_account_health WHERE is_latest")

last, year_ago = bridge.iloc[-1], bridge.iloc[-13]
ret_all = retention[retention["segment"] == "All"]
ret_now, ret_prev = ret_all.iloc[-1], ret_all.iloc[-13]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("ARR", money(last["ending_arr"]),
          f"{last['ending_arr'] / year_ago['ending_arr'] - 1:+.0%} vs last year")
c2.metric("Customers", f"{last['customers']:,}", f"{last['customers'] - year_ago['customers']:+,}")
c3.metric("Net revenue retention", f"{ret_now['nrr']:.0%}",
          f"{(ret_now['nrr'] - ret_prev['nrr']) * 100:+.1f} pts", help="12-month NRR. Target: 100%+")
c4.metric("Gross revenue retention", f"{ret_now['grr']:.0%}",
          f"{(ret_now['grr'] - ret_prev['grr']) * 100:+.1f} pts", help="12-month GRR. Target: about 90%")
high = health_now[health_now["risk_tier"] == "High"]
c5.metric("ARR at risk", money(health_now["arr_at_risk"].sum()),
          f"{len(high)} high-risk accounts", delta_color="off",
          help="Sum of churn probability x ARR across all current accounts")

st.caption(f"As of {last['month_start']:%B %Y}. Retention compares ARR with 12 months earlier, "
           "for customers who were paying then.")

# --- ARR bridge --------------------------------------------------------------------
st.subheader("Where ARR came from and where it went")
recent = bridge[bridge["month_start"] >= "2023-01-01"]
fig = go.Figure()
for col, name, color in [
    ("new_arr", "New", "#00798c"),
    ("expansion_arr", "Expansion", "#7fc8a9"),
    ("contraction_arr", "Contraction", "#edae49"),
    ("churned_arr", "Churn", "#d1495b"),
]:
    fig.add_bar(x=recent["month_start"], y=recent[col], name=name, marker_color=color)
fig.update_layout(barmode="relative", height=360, margin=dict(t=10, b=10),
                  yaxis_title="ARR change ($)", legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig, width="stretch")
st.caption("Bars above zero add ARR, bars below zero remove it. Churn spikes follow the annual "
           "renewal calendar, since customers can only leave at renewal.")

# --- Retention by segment ----------------------------------------------------------
left, right = st.columns([3, 2])
with left:
    st.subheader("12-month retention by segment")
    metric = st.radio("Metric", ["grr", "nrr"], horizontal=True,
                      format_func=lambda m: {"grr": "Gross (GRR)", "nrr": "Net (NRR)"}[m])
    fig = go.Figure()
    for seg in ["All", *SEGMENTS]:
        d = retention[retention["segment"] == seg]
        fig.add_scatter(x=d["month_start"], y=d[metric], name=seg, mode="lines",
                        line=dict(color=SEGMENT_COLORS[seg], width=3 if seg == "All" else 1.5))
    fig.add_hline(y=1.0, line_dash="dot", line_color="grey")
    fig.update_layout(height=340, margin=dict(t=10, b=10), yaxis_tickformat=".0%",
                      legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, width="stretch")
with right:
    st.subheader("Latest by segment")
    latest = retention[retention["month_start"] == retention["month_start"].max()]
    st.dataframe(
        latest[["segment", "starting_customers", "retained_customers", "nrr", "grr"]],
        hide_index=True, width="stretch",
        column_config={
            "segment": "Segment",
            "starting_customers": st.column_config.NumberColumn("Customers 12 mo ago"),
            "retained_customers": st.column_config.NumberColumn("Still customers"),
            "nrr": st.column_config.NumberColumn("NRR", format="percent"),
            "grr": st.column_config.NumberColumn("GRR", format="percent"),
        },
    )
    st.info("**Takeaway:** SMB loses the most customers, but Enterprise churn costs the most ARR. "
            "See the Risk List for which accounts to act on this month.")

footer()
