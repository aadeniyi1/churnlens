"""Risk list: the page a customer success leader opens every Monday."""

import streamlit as st

from data import SEGMENTS, footer, money, query

st.set_page_config(page_title="Risk list · ChurnLens", page_icon="📉", layout="wide")
st.title("Risk list")
st.caption("Every current customer, ranked by ARR at risk (churn probability x ARR). "
           "Start at the top: these accounts have the most revenue on the line.")

risk = query("""
    SELECT h.account_id, a.account_name, a.segment, a.region, c.csm_name,
           h.arr, h.churn_probability, h.arr_at_risk, h.risk_tier,
           h.health_score, h.health_tier, h.months_to_renewal, h.top_reasons
    FROM fact_account_health h
    JOIN dim_account a ON a.account_id = h.account_id
    LEFT JOIN dim_csm c ON c.csm_id = a.csm_id
    WHERE h.is_latest
""")

# --- Filters -------------------------------------------------------------------------
f1, f2, f3, f4 = st.columns(4)
segments = f1.multiselect("Segment", SEGMENTS, default=SEGMENTS)
tiers = f2.multiselect("Risk tier", ["High", "Medium", "Low"], default=["High", "Medium"])
csm = f3.selectbox("CSM", ["All CSMs", *sorted(risk["csm_name"].dropna().unique())])
renewal_within = f4.slider("Renews within (months)", 1, 12, 12)

view = risk[
    risk["segment"].isin(segments)
    & risk["risk_tier"].isin(tiers)
    & (risk["months_to_renewal"] <= renewal_within)
]
if csm != "All CSMs":
    view = view[view["csm_name"] == csm]
view = view.sort_values("arr_at_risk", ascending=False)

# --- Summary ---------------------------------------------------------------------------
k1, k2, k3, k4 = st.columns(4)
k1.metric("Accounts shown", f"{len(view):,}")
k2.metric("ARR in view", money(view["arr"].sum()))
k3.metric("ARR at risk in view", money(view["arr_at_risk"].sum()))
k4.metric("Renewing in 3 months or less", f"{(view['months_to_renewal'] <= 3).sum():,}")

st.dataframe(
    view.drop(columns=["account_id"]),
    hide_index=True, width="stretch", height=560,
    column_config={
        "account_name": st.column_config.TextColumn("Account", width="medium"),
        "segment": "Segment",
        "region": "Region",
        "csm_name": "CSM",
        "arr": st.column_config.NumberColumn("ARR", format="dollar"),
        "churn_probability": st.column_config.ProgressColumn(
            "Churn probability", min_value=0, max_value=1, format="percent"),
        "arr_at_risk": st.column_config.NumberColumn("ARR at risk", format="dollar"),
        "risk_tier": "Risk",
        "health_score": st.column_config.NumberColumn("Health (0-100)", format="%.0f"),
        "health_tier": "Health tier",
        "months_to_renewal": st.column_config.NumberColumn("Months to renewal"),
        "top_reasons": st.column_config.TextColumn("Why it's flagged", width="large"),
    },
)
st.caption("Churn probability comes from the machine-learning model. Health score and reasons come "
           "from the explainable rule-based score. See the Model page for how each was tested. "
           "Open an account on the Account 360 page.")
footer()
