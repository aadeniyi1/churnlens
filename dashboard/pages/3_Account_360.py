"""Account 360: everything about one customer on one page."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data import RISK_COLORS, footer, money, query

st.set_page_config(page_title="Account 360 · ChurnLens", page_icon="📉", layout="wide")
st.title("Account 360")

# Accounts listed riskiest first, so the default selection is the most urgent one.
accounts = query("""
    SELECT a.account_id, a.account_name, coalesce(h.arr_at_risk, 0) AS arr_at_risk
    FROM dim_account a
    LEFT JOIN fact_account_health h ON h.account_id = a.account_id AND h.is_latest
    ORDER BY arr_at_risk DESC, a.account_name
""")
labels = dict(zip(accounts["account_id"], accounts["account_name"] + "  (" + accounts["account_id"] + ")"))
account_id = st.selectbox("Account (type to search)", accounts["account_id"], format_func=labels.get)

info = query("""
    SELECT a.*, c.csm_name, c.team
    FROM dim_account a LEFT JOIN dim_csm c ON c.csm_id = a.csm_id
    WHERE a.account_id = ?
""", (account_id,)).iloc[0]
health = query("SELECT * FROM fact_account_health WHERE account_id = ? ORDER BY month_start", (account_id,))
months = query("SELECT * FROM mart_account_month WHERE account_id = ? ORDER BY month_start", (account_id,))
contracts = query("""
    SELECT c.contract_number, p.product_name, c.start_date, c.end_date, c.seats, c.arr, c.renewal_outcome
    FROM fact_contract c JOIN dim_product p ON p.product_id = c.product_id
    WHERE c.account_id = ? ORDER BY c.contract_number
""", (account_id,))
tickets = query("""
    SELECT ticket_id, created_at, priority, category, status, first_response_hours, sla_breached, csat
    FROM fact_ticket WHERE account_id = ? ORDER BY created_at DESC
""", (account_id,))

# --- Header ---------------------------------------------------------------------------
st.subheader(info["account_name"])
has_parent = pd.notna(info["parent_account_name"])
parent = f" · Subsidiary of **{info['parent_account_name']}**" if has_parent else ""
kids = f" · Parent of **{info['child_accounts']}** subsidiaries" if info["child_accounts"] else ""
st.markdown(f"{info['segment']} · {info['industry']} · {info['region']} · CSM **{info['csm_name']}** "
            f"· Customer since {info['first_contract_date']:%b %Y}{parent}{kids}")

if health.empty or not health["is_latest"].any():
    st.warning("This account is not a current customer, so it has no current risk score. "
               "Its history is shown below.")
else:
    now = health[health["is_latest"]].iloc[0]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("ARR", money(now["arr"]))
    k2.metric("Churn probability", f"{now['churn_probability']:.0%}", now["risk_tier"] + " risk",
              delta_color="inverse" if now["risk_tier"] != "Low" else "normal")
    k3.metric("Health score", f"{now['health_score']:.0f} / 100", now["health_tier"], delta_color="off")
    k4.metric("Renewal in", f"{now['months_to_renewal']} months")
    if pd.notna(now["top_reasons"]) and now["top_reasons"]:
        st.markdown("**Why it's flagged:**")
        for r in now["top_reasons"].split(" | "):
            st.markdown(f"- {r}")
    else:
        st.success("No warning signs right now.")

# --- Trends ----------------------------------------------------------------------------
left, right = st.columns(2)
with left:
    st.markdown("**Seat utilization** (monthly active users / licensed seats)")
    fig = go.Figure()
    fig.add_scatter(x=months["month_start"], y=months["seat_utilization"], mode="lines+markers",
                    line=dict(color="#00798c"))
    fig.add_hrect(y0=0, y1=0.40, fillcolor="#d1495b", opacity=0.08, line_width=0)
    fig.update_layout(height=280, margin=dict(t=10, b=10), yaxis_tickformat=".0%", yaxis_range=[0, 1.05])
    st.plotly_chart(fig, width="stretch")
with right:
    st.markdown("**Churn probability over time**")
    fig = go.Figure()
    fig.add_scatter(x=health["month_start"], y=health["churn_probability"], mode="lines+markers",
                    line=dict(color=RISK_COLORS["High"]))
    fig.add_hline(y=0.5, line_dash="dot", line_color="grey", annotation_text="High risk")
    fig.update_layout(height=280, margin=dict(t=10, b=10), yaxis_tickformat=".0%", yaxis_range=[0, 1])
    st.plotly_chart(fig, width="stretch")

# --- Contracts and tickets ---------------------------------------------------------------
st.markdown("**Contracts**")
st.dataframe(contracts, hide_index=True, width="stretch", column_config={
    "contract_number": "#", "product_name": "Plan", "start_date": st.column_config.DateColumn("Start"),
    "end_date": st.column_config.DateColumn("End"), "seats": "Seats",
    "arr": st.column_config.NumberColumn("ARR", format="dollar"), "renewal_outcome": "Outcome"})

st.markdown(f"**Support tickets** ({len(tickets)} total, newest first)")
st.dataframe(tickets.head(25), hide_index=True, width="stretch", column_config={
    "ticket_id": "Ticket", "created_at": st.column_config.DatetimeColumn("Opened", format="YYYY-MM-DD"),
    "priority": "Priority", "category": "Category", "status": "Status",
    "first_response_hours": st.column_config.NumberColumn("First response (h)", format="%.1f"),
    "sla_breached": "SLA missed", "csat": "CSAT"})
footer()
