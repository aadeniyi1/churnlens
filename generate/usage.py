"""
generate/usage.py: creates product telemetry, one month at a time.

Reads:   data/raw/contracts.parquet, data/raw/_truth/contract_truth.parquet
Outputs: data/raw/events/events_YYYY-MM.parquet   one file per month (~40k rows each)
         data/raw/_truth/account_month_state.parquet   hidden monthly state per account

Each row in an events file is one "key action" a user took in the product, such
as viewing a report or creating a dashboard. Columns:
    event_id, account_id, user_id, product_id, event_type, event_ts

WHY ONE MONTH AT A TIME? Your laptop has 8 GB of RAM. Building all ~1.5M events
in memory at once would work, but it is a bad habit. Writing each month to its
own file and then forgetting it keeps memory flat no matter how many months we
add. This is called "chunked processing" and it is how real pipelines scale.

THE STORY THE DATA TELLS:
    - Each month, an account's "utilization" (share of seats actually used)
      depends on its hidden risk: healthy accounts use ~85% of seats, risky ones much less.
    - In the 6 months before a (non-surprise) churn, usage falls steadily.
    - Brand-new customers ramp up over their first two months.
    - Healthy accounts use "sticky" features (dashboards, integrations) more.
"""

import numpy as np
import pandas as pd

import config

EVENT_TYPES = np.array(
    ["login", "report_viewed", "dashboard_created", "export_csv", "integration_sync", "admin_settings"]
)


def monthly_state(contracts: pd.DataFrame, month: pd.Period, rng: np.random.Generator) -> pd.DataFrame:
    """
    For one month, return one row per account with an active contract, holding
    that account's seats and how many users were active.
    """
    month_start = month.to_timestamp()
    # Contracts always start on the 1st, so "active this month" is simply:
    active = contracts[(contracts["start_date"] <= month_start) & (contracts["end_date"] >= month_start)].copy()
    if active.empty:
        return active

    # How many months are left on the contract, counting this one (12 ... 1).
    end_month = active["end_date"].dt.to_period("M")
    active["months_to_end"] = (end_month - month).apply(lambda d: d.n) + 1
    # How many months since the contract began (0 = first month).
    active["months_in"] = (month - active["start_date"].dt.to_period("M")).apply(lambda d: d.n)

    r = active["term_risk"].to_numpy()

    # Base utilization: about 0.85 for a very healthy account, about 0.30 for a very risky one.
    util = 0.88 - 0.65 * r + rng.normal(0, 0.07, size=len(active))

    # Usage collapses in the run-up to a churn the data CAN predict.
    declining = (
        (active["renewal_outcome"] == "churned")
        & (~active["surprise_churn"])
        & (active["months_to_end"] <= 6)
    ).to_numpy()
    decline_factor = np.maximum(0.25, 1 - 0.12 * (7 - active["months_to_end"].to_numpy()))
    util = np.where(declining, util * decline_factor, util)

    # A milder dip before a customer shrinks their contract.
    shrinking = ((active["renewal_outcome"] == "contracted") & (active["months_to_end"] <= 4)).to_numpy()
    util = np.where(shrinking, util * 0.9, util)

    # Onboarding ramp: a new customer's first two months are quieter.
    first = (active["contract_number"] == 1).to_numpy()
    months_in = active["months_in"].to_numpy()
    util = np.where(first & (months_in == 0), util * 0.55, util)
    util = np.where(first & (months_in == 1), util * 0.80, util)

    util = np.clip(util, 0.02, 1.0)
    active["utilization"] = util.round(4)
    # Each seat is "used" this month with probability = utilization.
    active["active_users"] = rng.binomial(active["seats"].to_numpy(), util)
    active["in_decline"] = declining
    active["month"] = month_start
    return active


def events_for_month(state: pd.DataFrame, month: pd.Period, rng: np.random.Generator) -> pd.DataFrame:
    """Turn one month of account state into individual event rows."""
    state = state[state["active_users"] > 0]
    k = state["active_users"].to_numpy()

    # --- 1) One row per active user -------------------------------------
    # np.repeat copies each account's row once per active user.
    acc_idx = np.repeat(np.arange(len(state)), k)
    # Which users were active? Take a block of k user numbers starting at a random
    # offset, wrapping around the seat count, so different users show up each month.
    seats = state["seats"].to_numpy()[acc_idx]
    offset = rng.integers(0, state["seats"].to_numpy() + 1)[acc_idx]
    position = np.arange(len(acc_idx)) - np.repeat(np.cumsum(k) - k, k)  # 0..k-1 within account
    user_num = (offset + position) % seats + 1

    # --- 2) Several events per user -------------------------------------
    util = state["utilization"].to_numpy()[acc_idx]
    # Every active user has at least one event; engaged accounts have more.
    lam = (config.EVENTS_PER_ACTIVE_USER - 1) * (0.5 + util)
    per_user = 1 + rng.poisson(lam)
    user_rows = np.repeat(np.arange(len(acc_idx)), per_user)
    acc_rows = acc_idx[user_rows]
    u = util[user_rows]
    n = len(user_rows)

    # --- 3) Event type, with healthier accounts using sticky features more ---
    weights = np.column_stack(
        [
            np.full(n, 0.35),  # login
            np.full(n, 0.25),  # report_viewed
            0.08 + 0.12 * u,  # dashboard_created  (sticky)
            np.full(n, 0.10),  # export_csv
            0.05 + 0.10 * u,  # integration_sync   (sticky)
            np.full(n, 0.05),  # admin_settings
        ]
    )
    cum = np.cumsum(weights / weights.sum(axis=1, keepdims=True), axis=1)
    pick = (rng.random(n)[:, None] > cum).sum(axis=1)  # index of the chosen type
    pick = np.minimum(pick, len(EVENT_TYPES) - 1)

    # --- 4) A random moment inside the month ----------------------------
    seconds_in_month = month.days_in_month * 24 * 3600
    ts = month.to_timestamp() + pd.to_timedelta(rng.integers(0, seconds_in_month, size=n), unit="s")

    account_ids = state["account_id"].to_numpy()[acc_rows]
    events = pd.DataFrame(
        {
            "event_id": [f"EVT-{month.strftime('%Y%m')}-{i:07d}" for i in range(n)],
            "account_id": account_ids,
            "user_id": [f"{a}-U{num:04d}" for a, num in zip(account_ids, user_num[user_rows])],
            "product_id": state["product_id"].to_numpy()[acc_rows],
            "event_type": EVENT_TYPES[pick],
            "event_ts": ts,
        }
    )

    # --- 5) Messy data on purpose: a few events get delivered twice ------
    dupes = events.sample(frac=config.DUPLICATE_EVENT_RATE, random_state=int(rng.integers(1e9)))
    events = pd.concat([events, dupes], ignore_index=True)
    return events.sort_values("event_ts", ignore_index=True)


def main() -> None:
    rng = np.random.default_rng(config.SEED + 2)

    contracts = pd.read_parquet(config.RAW_DIR / "contracts.parquet")
    truth = pd.read_parquet(config.TRUTH_DIR / "contract_truth.parquet")
    contracts = contracts.merge(truth, on="contract_id")
    contracts["start_date"] = pd.to_datetime(contracts["start_date"])
    contracts["end_date"] = pd.to_datetime(contracts["end_date"])

    # Start clean so a smaller re-run never leaves old months behind.
    config.EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    for old in config.EVENTS_DIR.glob("events_*.parquet"):
        old.unlink()

    months = pd.period_range(config.TELEMETRY_START, config.TELEMETRY_END, freq="M")
    all_state = []
    total = 0
    for month in months:
        state = monthly_state(contracts, month, rng)
        if state.empty:
            continue
        events = events_for_month(state, month, rng)
        events.to_parquet(config.EVENTS_DIR / f"events_{month.strftime('%Y-%m')}.parquet", index=False)
        total += len(events)
        # Keep only the small per-account summary; the big events table is dropped here.
        all_state.append(
            state[["account_id", "month", "contract_id", "seats", "utilization",
                   "active_users", "term_risk", "in_decline"]]
        )
        del events

    pd.concat(all_state, ignore_index=True).to_parquet(
        config.TRUTH_DIR / "account_month_state.parquet", index=False
    )
    print(f"  events:    {total:,} across {len(months)} monthly files")


if __name__ == "__main__":
    main()
