"""
model/features.py: turns the warehouse into model-ready features.

One row = one account in one month (a "snapshot"). Each row describes what a CSM
could see about that account at the END of that month, using only that month and
the months before it. Nothing from the future is allowed in. Using future data by
accident is called "leakage", and it makes a model look brilliant in testing and
useless in real life.

The features come straight from what the Phase 3 analysis found matters:
    usage          seat utilization now, and how it changed vs. 3 months earlier
    early usage    utilization in the account's first 90 days
    stickiness     share of activity in sticky features (dashboards, integrations)
    support        tickets and urgent tickets per 10 seats, SLA breach rate, CSAT (last 3 months)
    contract       months to renewal, tenure, size (ARR, seats), segment, past contraction

TRAINING ROWS use only snapshots taken 3 or more months before the renewal date
(about 90 days or more), so the model learns from information early enough to act on.
The label is whether that contract churned at its renewal.
"""

import duckdb
import numpy as np
import pandas as pd

import config

# The numeric columns the model uses. Segment is added separately (one-hot encoded).
NUMERIC_FEATURES = [
    "util_3m",              # average seat utilization, last 3 months
    "util_change_3m",       # util_3m minus the 3 months before that (negative = falling)
    "early_utilization",    # average utilization in the account's first 3 months
    "key_feature_share_3m", # share of events that are dashboards/integrations
    "tickets_per_10_seats_3m",   # ticket volume relative to account size
    "urgent_per_10_seats_3m",    # big accounts file more tickets just by being big
    "sla_breach_rate_3m",
    "csat_3m",
    "csat_missing",         # 1 if no survey answers in 3 months (we filled csat_3m in)
    "months_to_renewal",
    "tenure_months",
    "log_arr",
    "licensed_seats",
    "contracted_last_renewal",
]
CATEGORICAL_FEATURES = ["segment"]
MIN_MONTHS_TO_RENEWAL = 3  # "at least 90 days before renewal"

FEATURE_SQL = """
WITH early AS (
    -- Average utilization over the account's first 3 months as a customer.
    -- Only known once those 3 months have passed, so it is joined with that condition below.
    SELECT account_id, avg(seat_utilization) AS early_utilization
    FROM mart_account_month
    WHERE tenure_months BETWEEN 0 AND 2
    GROUP BY account_id
    HAVING count(*) = 3
),
windows AS (
    SELECT
        m.*,
        -- "ROWS BETWEEN 2 PRECEDING AND CURRENT ROW" = this month and the 2 before it.
        avg(seat_utilization) OVER last3                       AS util_3m,
        avg(seat_utilization) OVER prev3                       AS util_prev_3m,
        sum(tickets) OVER last3                                AS tickets_3m,
        sum(urgent_tickets) OVER last3                         AS urgent_tickets_3m,
        sum(sla_breaches) OVER last3                           AS sla_breaches_3m,
        sum(csat_responses * avg_csat) OVER last3
            / nullif(sum(csat_responses) OVER last3, 0)        AS csat_3m,
        sum(key_feature_events) OVER last3
            / nullif(sum(events) OVER last3, 0)                AS key_feature_share_3m,
        count(*) OVER last6                                    AS months_of_history
    FROM mart_account_month m
    WINDOW
        last3 AS (PARTITION BY account_id ORDER BY month_start ROWS BETWEEN 2 PRECEDING AND CURRENT ROW),
        prev3 AS (PARTITION BY account_id ORDER BY month_start ROWS BETWEEN 5 PRECEDING AND 3 PRECEDING),
        last6 AS (PARTITION BY account_id ORDER BY month_start ROWS BETWEEN 5 PRECEDING AND CURRENT ROW)
)
SELECT
    w.account_id,
    w.month_start,
    w.contract_id,
    w.segment,
    w.arr,
    w.licensed_seats,
    w.months_to_renewal,
    w.tenure_months,
    w.util_3m,
    w.util_3m - w.util_prev_3m                                 AS util_change_3m,
    -- early_utilization only counts once the first 3 months are over
    CASE WHEN w.tenure_months >= 2 THEN e.early_utilization END AS early_utilization,
    coalesce(w.key_feature_share_3m, 0)                        AS key_feature_share_3m,
    w.tickets_3m,
    w.urgent_tickets_3m,
    coalesce(w.sla_breaches_3m / nullif(w.tickets_3m, 0), 0)  AS sla_breach_rate_3m,
    w.csat_3m,
    coalesce(c.arr_change < 0, false)::INT                     AS contracted_last_renewal,
    c.renewal_outcome
FROM windows w
LEFT JOIN early e        ON e.account_id = w.account_id
LEFT JOIN fact_contract c ON c.contract_id = w.contract_id
WHERE w.months_of_history = 6   -- need 6 months of history to measure a 3-month change
"""


def load_snapshots(con: duckdb.DuckDBPyConnection | None = None) -> pd.DataFrame:
    """Every account-month snapshot with its features, plus the contract's outcome."""
    close = con is None
    con = con or duckdb.connect(str(config.WAREHOUSE_PATH), read_only=True)
    df = con.sql(FEATURE_SQL).df()
    if close:
        con.close()

    # Fill gaps with sensible neutral values, and keep a flag where that matters.
    df["csat_missing"] = df["csat_3m"].isna().astype(int)
    df["csat_3m"] = df["csat_3m"].fillna(df["csat_3m"].median())
    df["early_utilization"] = df["early_utilization"].fillna(df["util_3m"])
    df["log_arr"] = np.log1p(df["arr"])  # ARR is very skewed; the log evens it out
    # A 200-seat customer naturally files more tickets than a 5-seat one. Dividing by
    # size stops the model from treating "big" as "unhappy".
    df["tickets_per_10_seats_3m"] = 10 * df["tickets_3m"] / df["licensed_seats"]
    df["urgent_per_10_seats_3m"] = 10 * df["urgent_tickets_3m"] / df["licensed_seats"]
    return df


def training_rows(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Snapshots we can learn from: outcome known, and taken 90+ days before renewal."""
    df = snapshots[
        (snapshots["renewal_outcome"] != "open")
        & (snapshots["months_to_renewal"] >= MIN_MONTHS_TO_RENEWAL)
    ].copy()
    df["churned"] = (df["renewal_outcome"] == "churned").astype(int)
    return df


if __name__ == "__main__":
    snaps = load_snapshots()
    train = training_rows(snaps)
    print(f"snapshots: {len(snaps):,}   training rows: {len(train):,}   "
          f"churn rate: {train['churned'].mean():.1%}")
    print(train[NUMERIC_FEATURES].describe().T.round(3))
