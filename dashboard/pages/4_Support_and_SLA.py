"""Support and SLA: are we answering customers fast enough, and does it matter for churn?"""

import plotly.express as px
import streamlit as st

from data import RISK_COLORS, SEGMENTS, footer, query

st.set_page_config(page_title="Support and SLA · ChurnLens", page_icon="📉", layout="wide")
st.title("Support and SLA")
st.caption("First-response targets: P1 within 1 hour, P2 within 4 hours, P3 within 24 hours.")

segments = st.multiselect("Segments", SEGMENTS, default=SEGMENTS)
tickets = query("""
    SELECT t.created_month, t.priority, t.sla_breached, t.csat, a.segment
    FROM fact_ticket t JOIN dim_account a ON a.account_id = t.account_id
    WHERE t.first_response_at IS NOT NULL
""")
tickets = tickets[tickets["segment"].isin(segments)]

k1, k2, k3 = st.columns(3)
k1.metric("Tickets (all time)", f"{len(tickets):,}")
k2.metric("SLA attainment", f"{1 - tickets['sla_breached'].mean():.1%}")
answered = tickets["csat"].dropna()
k3.metric("CSAT (share of 4s and 5s)", f"{(answered >= 4).mean():.0%}",
          help=f"Based on {len(answered):,} survey answers")

left, right = st.columns(2)
with left:
    st.markdown("**SLA attainment by priority, per month**")
    sla = (tickets.groupby(["created_month", "priority"])["sla_breached"].mean()
           .rsub(1).rename("attainment").reset_index())
    fig = px.line(sla, x="created_month", y="attainment", color="priority",
                  color_discrete_map={"P1": RISK_COLORS["High"], "P2": RISK_COLORS["Medium"],
                                      "P3": RISK_COLORS["Low"]})
    fig.update_layout(height=320, margin=dict(t=10, b=10), yaxis_tickformat=".0%",
                      xaxis_title=None, yaxis_title="Answered within SLA")
    st.plotly_chart(fig, width="stretch")
with right:
    st.markdown("**Average CSAT per month**")
    csat = tickets.dropna(subset=["csat"]).groupby("created_month")["csat"].mean().reset_index()
    fig = px.line(csat, x="created_month", y="csat")
    fig.update_traces(line_color="#30343f")
    fig.update_layout(height=320, margin=dict(t=10, b=10), yaxis_range=[1, 5],
                      xaxis_title=None, yaxis_title="CSAT (1-5)")
    st.plotly_chart(fig, width="stretch")

# --- Does support quality relate to churn? ----------------------------------------------
st.markdown("**Does support experience relate to churn?**")
st.caption("For every contract that reached renewal: the share of its tickets that missed SLA in "
           "the 6 months before renewal, and whether the customer churned.")
link = query("""
    SELECT m.contract_id,
           sum(m.sla_breaches) * 1.0 / nullif(sum(m.tickets), 0) AS breach_rate,
           max(CASE WHEN c.renewal_outcome = 'churned' THEN 1 ELSE 0 END) AS churned
    FROM mart_account_month m
    JOIN fact_contract c ON c.contract_id = m.contract_id
    WHERE c.renewal_outcome <> 'open' AND m.months_to_renewal <= 6
    GROUP BY m.contract_id
""").dropna()
link["band"] = link["breach_rate"].map(
    lambda r: "0% missed" if r == 0 else "1-49% missed" if r < 0.5 else "50%+ missed")
bands = link.groupby("band")["churned"].agg(["mean", "count"]).reindex(
    ["0% missed", "1-49% missed", "50%+ missed"]).reset_index()
fig = px.bar(bands, x="band", y="mean", text_auto=".0%", hover_data={"count": True})
fig.update_traces(marker_color=RISK_COLORS["High"])
fig.update_layout(height=300, margin=dict(t=10, b=10), yaxis_tickformat=".0%",
                  xaxis_title="Tickets missing SLA in the 6 months before renewal",
                  yaxis_title="Churn rate at renewal")
st.plotly_chart(fig, width="stretch")
footer()
