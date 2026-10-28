"""Cohort retention: for customers who signed in the same quarter, how much is left N months later?"""

import plotly.express as px
import streamlit as st

from data import SEGMENTS, footer, query

st.set_page_config(page_title="Cohort retention · ChurnLens", page_icon="📉", layout="wide")
st.title("Cohort retention")
st.caption("Each row is a group of customers who signed in the same quarter. Each cell shows how much "
           "of that group is still with us after N months. Read across a row to follow one cohort.")

c1, c2 = st.columns(2)
segments = c1.multiselect("Segments", SEGMENTS, default=SEGMENTS)
measure = c2.radio("Measure", ["ARR retained", "Customers retained"], horizontal=True)

if not segments:
    st.warning("Pick at least one segment.")
    st.stop()

cohorts = query("SELECT * FROM mart_cohort_retention")
cohorts = cohorts[cohorts["segment"].isin(segments)]

# Add up the chosen segments, then divide, so the percentages are correct for the combination.
grouped = cohorts.groupby(["cohort_quarter", "months_since_start"]).agg(
    retained_arr=("retained_arr", "sum"), start_arr=("cohort_starting_arr", "sum"),
    retained_accounts=("retained_accounts", "sum"), start_accounts=("cohort_accounts", "sum"),
).reset_index()
if measure == "ARR retained":
    grouped["value"] = grouped["retained_arr"] / grouped["start_arr"]
else:
    grouped["value"] = grouped["retained_accounts"] / grouped["start_accounts"]

grid = grouped.pivot(index="cohort_quarter", columns="months_since_start", values="value")
grid = grid[[c for c in grid.columns if c % 3 == 0]]  # every 3rd month keeps it readable

fig = px.imshow(grid, color_continuous_scale="YlGnBu", zmin=0.5, zmax=1.1, aspect="auto",
                text_auto=".0%", labels=dict(x="Months since first contract", y="Signup cohort",
                                             color=measure))
fig.update_layout(height=560, margin=dict(t=10, b=10), coloraxis_colorbar_tickformat=".0%")
st.plotly_chart(fig, width="stretch")

st.info("**How to read it:** cells only change at months 12, 24 and 36, because contracts are "
        "annual and customers can only leave at renewal. The first renewal causes the biggest drop, "
        "so onboarding in the first year matters most.")
footer()
