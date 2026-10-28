"""
model/health_score.py: a rule-based account health score from 0 to 100.

Why have rules when we also have a machine-learning model? Because CS teams only
act on a score they can explain to a customer and to their boss. The health score
is the "explainable" view, and the churn model is the "most accurate" view. The
dashboard shows both, and the model card compares them.

    health = 35% usage trend + 25% seat utilization + 25% support experience + 15% contract signals

Each part is scored 0-100 (100 = healthy):
    usage trend      utilization change over 3 months. Flat = 60, -20 points = 0, +10 points = 100
    utilization      seat utilization, where 80% or more = 100
    support          starts at 100. Loses points for SLA breaches, low CSAT, urgent tickets
    contract         starts at 100. Loses points for shrinking at last renewal, or being under a year old

Tiers:  Healthy >= 70   |   Watch 40-69   |   At risk < 40

reasons() turns the same signals into short sentences a CSM can read, such as
"Seat utilization is 32% (healthy is 55%+)".
"""

import numpy as np
import pandas as pd

WEIGHTS = {"usage_trend": 0.35, "utilization": 0.25, "support": 0.25, "contract": 0.15}
TIERS = [(70, "Healthy"), (40, "Watch"), (0, "At risk")]


def component_scores(f: pd.DataFrame) -> pd.DataFrame:
    """Score each part 0-100. `f` is the feature table from features.py."""
    out = pd.DataFrame(index=f.index)
    # np.interp maps a value onto a scale: here -0.20 -> 0, 0.00 -> 60, +0.10 -> 100
    out["usage_trend_score"] = np.interp(f["util_change_3m"], [-0.20, 0.0, 0.10], [0, 60, 100])
    out["utilization_score"] = np.interp(f["util_3m"], [0.0, 0.80], [0, 100])

    support = (
        100
        - 60 * f["sla_breach_rate_3m"]                                   # all tickets breached -> -60
        - 25 * np.clip(4.0 - f["csat_3m"], 0, None) * (1 - f["csat_missing"])  # each point below 4 -> -25
        - 8 * f["urgent_tickets_3m"]                                     # each P1/P2 ticket -> -8
    )
    out["support_score"] = np.clip(support, 0, 100)

    contract = 100 - 50 * f["contracted_last_renewal"] - 25 * (f["tenure_months"] < 12)
    out["contract_score"] = np.clip(contract, 0, 100)
    return out


def health_score(f: pd.DataFrame) -> pd.DataFrame:
    """Return the four component scores, the weighted total, and the tier."""
    out = component_scores(f)
    out["health_score"] = (
        WEIGHTS["usage_trend"] * out["usage_trend_score"]
        + WEIGHTS["utilization"] * out["utilization_score"]
        + WEIGHTS["support"] * out["support_score"]
        + WEIGHTS["contract"] * out["contract_score"]
    ).round(1)
    out["health_tier"] = pd.cut(
        out["health_score"], bins=[-1, 40, 70, 101], right=False, labels=["At risk", "Watch", "Healthy"]
    ).astype(str)
    return out


def reasons(f: pd.DataFrame, top_n: int = 3) -> pd.Series:
    """
    Up to `top_n` plain-English risk reasons per row, most serious first.

    Each rule gives a severity from 0 (fine) to 1 (very bad) and a sentence.
    We keep the worst ones. If nothing is wrong, the account gets no reasons.
    """
    rules = {
        "low_util": (
            np.clip((0.55 - f["util_3m"]) / 0.35, 0, 1),
            "Seat utilization is " + (f["util_3m"] * 100).round().astype(int).astype(str)
            + "% (healthy is 55%+)",
        ),
        "falling_util": (
            np.clip(-f["util_change_3m"] / 0.20, 0, 1),
            "Usage fell " + (-f["util_change_3m"] * 100).round().astype(int).astype(str)
            + " points in 3 months",
        ),
        "sla": (
            np.clip(f["sla_breach_rate_3m"] * f["tickets_3m"].clip(upper=3) / 3, 0, 1),
            f["sla_breach_rate_3m"].mul(100).round().astype(int).astype(str)
            + "% of recent tickets missed SLA",
        ),
        "csat": (
            np.clip((3.8 - f["csat_3m"]) / 1.5, 0, 1) * (1 - f["csat_missing"]),
            "Recent CSAT is " + f["csat_3m"].round(1).astype(str) + " / 5",
        ),
        "urgent": (
            np.clip(f["urgent_tickets_3m"] / 3, 0, 1),
            f["urgent_tickets_3m"].astype(int).astype(str) + " urgent (P1/P2) tickets in 3 months",
        ),
        "contracted": (
            f["contracted_last_renewal"] * 0.6,
            pd.Series("Reduced seats at last renewal", index=f.index),
        ),
        "slow_start": (
            np.clip((0.45 - f["early_utilization"]) / 0.25, 0, 1) * (f["tenure_months"] < 15),
            "Slow start: " + (f["early_utilization"] * 100).round().astype(int).astype(str)
            + "% utilization in first 90 days",
        ),
    }
    severity = pd.DataFrame({k: v[0] for k, v in rules.items()}, index=f.index)
    text = pd.DataFrame({k: v[1] for k, v in rules.items()}, index=f.index)

    def pick(i):
        s = severity.loc[i]
        worst = s[s > 0.15].sort_values(ascending=False).index[:top_n]  # ignore tiny issues
        return " | ".join(text.loc[i, worst])

    return pd.Series([pick(i) for i in f.index], index=f.index)
