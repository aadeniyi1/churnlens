"""Model and data quality: how good are the scores, and how fresh is the data?"""

import json

import pandas as pd
import plotly.express as px
import streamlit as st

from data import footer, query

st.set_page_config(page_title="Model and data · ChurnLens", page_icon="📉", layout="wide")
st.title("Model and data quality")

metrics = json.loads(query("SELECT metrics_json FROM model_metrics").iloc[0, 0])
best = metrics["best_model"]
r = metrics["results"][best]

st.markdown(f"**Model in use:** `{best}`. Tested on {metrics['test_contracts']:,} contracts renewing in "
            f"2025, scored 4 months before renewal. The model was trained only on earlier renewals.")
k1, k2, k3, k4 = st.columns(4)
k1.metric("ROC AUC", f"{r['roc_auc']:.2f}", help="0.5 = coin flip, 1.0 = perfect ranking")
k2.metric("Precision in top 10%", f"{r['precision_at_10pct']:.0%}",
          help="Of the 10% of accounts flagged riskiest, how many really churned")
k3.metric("Churned ARR caught in top 10%", f"{r['arr_captured_at_10pct']:.0%}")
k4.metric("Test churn rate", f"{metrics['test_churn_rate']:.0%}", help="The baseline to beat")

st.markdown("**Model comparison** (same test set)")
comparison = pd.DataFrame(metrics["results"]).T.reset_index(names="approach")
comparison["approach"] = comparison["approach"].map({
    "logistic_regression": "Logistic regression (baseline)",
    "gradient_boosting": "Gradient boosting",
    "health_score_rules": "Rule-based health score",
})
st.dataframe(comparison, hide_index=True, width="stretch", column_config={
    "approach": "Approach",
    "roc_auc": st.column_config.NumberColumn("ROC AUC", format="%.3f"),
    "pr_auc": st.column_config.NumberColumn("PR AUC", format="%.3f"),
    "brier": st.column_config.NumberColumn("Brier (lower is better)", format="%.3f"),
    "precision_at_10pct": st.column_config.NumberColumn("Precision @10%", format="percent"),
    "arr_captured_at_10pct": st.column_config.NumberColumn("ARR caught @10%", format="percent"),
})

left, right = st.columns(2)
with left:
    st.markdown("**What drives the model** (drop in ROC AUC when a feature is shuffled)")
    imp = pd.Series(metrics["feature_importance"]).sort_values().tail(8).reset_index()
    imp.columns = ["feature", "importance"]
    fig = px.bar(imp, x="importance", y="feature", orientation="h")
    fig.update_traces(marker_color="#00798c")
    fig.update_layout(height=320, margin=dict(t=10, b=10), yaxis_title=None)
    st.plotly_chart(fig, width="stretch")
with right:
    st.markdown("**Does the health score separate accounts?** Actual churn rate by tier, test set")
    tiers = pd.Series(metrics["churn_rate_by_health_tier"]).reindex(
        ["Healthy", "Watch", "At risk"]).reset_index()
    tiers.columns = ["tier", "churn_rate"]
    fig = px.bar(tiers, x="tier", y="churn_rate", text_auto=".0%", color="tier",
                 color_discrete_map={"Healthy": "#00798c", "Watch": "#edae49", "At risk": "#d1495b"})
    fig.update_layout(height=320, margin=dict(t=10, b=10), showlegend=False,
                      yaxis_tickformat=".0%", xaxis_title=None, yaxis_title="Churned at renewal")
    st.plotly_chart(fig, width="stretch")

st.divider()
st.subheader("Data freshness")
fresh = query("""
    SELECT max(month_start) AS latest_month, count(*) AS rows_scored, min(model_version) AS model_version
    FROM fact_account_health
""").iloc[0]
counts = {t: int(query(f"SELECT count(*) AS n FROM {t}").iloc[0, 0]) for t in
          ["dim_account", "fact_contract", "fact_ticket", "mart_account_month", "fact_account_health"]}
c1, c2, c3 = st.columns(3)
c1.metric("Data through", f"{fresh['latest_month']:%B %Y}")
c2.metric("Account-months scored", f"{fresh['rows_scored']:,}")
c3.metric("Model version", fresh["model_version"])
st.dataframe(pd.DataFrame(counts.items(), columns=["table", "rows"]), hide_index=True)
st.caption("The pipeline runs 18 data quality checks (unique keys, no orphan rows, a balanced ARR "
           "bridge, and more) before anything is published. A failed check stops the publish.")
footer()
