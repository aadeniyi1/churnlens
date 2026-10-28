"""
model/score.py: scores every account and saves the results in the warehouse.

Run it with:   uv run run.py model     (train.py runs first, then this)

Writes the table fact_account_health, with one row per account per month:
    health score (rules) + its 4 parts + tier      -> explainable view
    churn_probability (model) + risk tier           -> most accurate view
    arr_at_risk = churn_probability x ARR           -> what to prioritize by
    top_reasons (latest month only)                 -> what a CSM should look at

Scoring every month (not just the latest) lets the dashboard show how an
account's health changed over time.
"""

import duckdb
import joblib
import numpy as np
import pandas as pd

import config
from model.features import load_snapshots
from model.health_score import health_score, reasons
from model.train import METRICS_PATH, MODEL_PATH

RISK_TIERS = {"High": 0.50, "Medium": 0.25}  # churn probability cut-offs; below 0.25 = Low


def risk_tier(p: pd.Series) -> pd.Series:
    return pd.Series(
        np.select([p >= RISK_TIERS["High"], p >= RISK_TIERS["Medium"]], ["High", "Medium"], "Low"),
        index=p.index,
    )


def main() -> None:
    if not MODEL_PATH.exists():
        raise SystemExit("No trained model found. Run:  uv run run.py model")
    saved = joblib.load(MODEL_PATH)

    con = duckdb.connect(str(config.WAREHOUSE_PATH))
    snaps = load_snapshots(con)

    scores = health_score(snaps)
    out = pd.concat([snaps[["account_id", "month_start", "contract_id", "segment", "arr",
                            "months_to_renewal"]], scores], axis=1)
    out["churn_probability"] = saved["model"].predict_proba(snaps[saved["features"]])[:, 1].round(4)
    out["risk_tier"] = risk_tier(out["churn_probability"])
    out["arr_at_risk"] = (out["churn_probability"] * out["arr"]).round(2)
    out["model_version"] = f"{saved['name']}-v1"

    # Reasons are slower to build, and a CSM only needs today's, so: latest month only.
    latest_month = out["month_start"].max()
    latest = out["month_start"] == latest_month
    out["top_reasons"] = None
    out.loc[latest, "top_reasons"] = reasons(snaps[latest])
    out["is_latest"] = latest

    # Sanity checks: fail loudly instead of saving nonsense.
    assert out["churn_probability"].between(0, 1).all(), "probabilities must be 0-1"
    assert out["health_score"].between(0, 100).all(), "health scores must be 0-100"
    assert not out.duplicated(["account_id", "month_start"]).any(), "one row per account-month"

    con.register("scores_df", out)  # lets SQL see the pandas DataFrame as a table
    con.execute("CREATE OR REPLACE TABLE fact_account_health AS SELECT * FROM scores_df")

    # Save the model's test results next to the scores, so the dashboard can show them.
    con.execute("CREATE OR REPLACE TABLE model_metrics (metrics_json VARCHAR)")
    con.execute("INSERT INTO model_metrics VALUES (?)", [METRICS_PATH.read_text()])
    con.close()

    now = out[latest]
    print(f"  scored {len(out):,} account-months; {len(now):,} active accounts in {latest_month:%b %Y}")
    print(f"  risk tiers now: {now['risk_tier'].value_counts().to_dict()}")
    print(f"  ARR at risk now: ${now['arr_at_risk'].sum():,.0f} of ${now['arr'].sum():,.0f}")

    # Bonus check only possible with synthetic data: compare against the hidden truth.
    # A good model's risk ranking should line up with the secret risk value.
    truth = pd.read_parquet(config.TRUTH_DIR / "account_risk.parquet")
    check = now.merge(truth, on="account_id")
    corr = check["churn_probability"].rank().corr(check["risk"].rank())
    print(f"  rank correlation between model risk and hidden true risk: {corr:.2f}")


if __name__ == "__main__":
    main()
