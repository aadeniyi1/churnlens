"""
tests/test_model.py: sanity checks for the health score and its reasons.

These use two hand-made accounts, one clearly healthy and one clearly in trouble,
so they run instantly and don't need the warehouse.
"""

import pandas as pd

from model.features import MIN_MONTHS_TO_RENEWAL, training_rows
from model.health_score import health_score, reasons

HEALTHY = {
    "util_3m": 0.85, "util_change_3m": 0.02, "early_utilization": 0.80, "key_feature_share_3m": 0.30,
    "tickets_3m": 1, "urgent_tickets_3m": 0, "sla_breach_rate_3m": 0.0, "csat_3m": 4.6,
    "csat_missing": 0, "tenure_months": 30, "contracted_last_renewal": 0,
}
TROUBLED = {
    "util_3m": 0.25, "util_change_3m": -0.18, "early_utilization": 0.35, "key_feature_share_3m": 0.15,
    "tickets_3m": 6, "urgent_tickets_3m": 3, "sla_breach_rate_3m": 0.5, "csat_3m": 2.5,
    "csat_missing": 0, "tenure_months": 10, "contracted_last_renewal": 1,
}


def accounts() -> pd.DataFrame:
    return pd.DataFrame([HEALTHY, TROUBLED], index=["healthy", "troubled"])


def test_scores_are_between_0_and_100():
    scores = health_score(accounts())
    assert scores["health_score"].between(0, 100).all()


def test_healthy_account_scores_higher():
    scores = health_score(accounts())
    assert scores.loc["healthy", "health_score"] > scores.loc["troubled", "health_score"]
    assert scores.loc["healthy", "health_tier"] == "Healthy"
    assert scores.loc["troubled", "health_tier"] == "At risk"


def test_reasons_explain_the_trouble():
    r = reasons(accounts())
    assert r["healthy"] == ""  # nothing to flag
    flagged = r["troubled"].split(" | ")
    assert len(flagged) == 3  # top 3 only
    assert any("utilization" in reason.lower() or "usage" in reason.lower() for reason in flagged)


def test_training_rows_exclude_open_contracts_and_late_snapshots():
    snaps = pd.DataFrame({
        "renewal_outcome": ["churned", "renewed", "open", "churned"],
        "months_to_renewal": [6, 4, 6, 1],  # the last one is too close to renewal
    })
    rows = training_rows(snaps)
    assert len(rows) == 2
    assert (rows["months_to_renewal"] >= MIN_MONTHS_TO_RENEWAL).all()
    assert rows["churned"].tolist() == [1, 0]
