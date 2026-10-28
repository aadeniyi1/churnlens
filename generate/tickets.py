"""
generate/tickets.py: creates support tickets (the "help desk" system).

Reads:   data/raw/_truth/account_month_state.parquet   (written by usage.py)
Outputs: data/raw/tickets.parquet

Columns:
    ticket_id, account_id, priority (P1 most urgent ... P3), category, status,
    created_at, first_response_at, resolved_at, updated_at, csat (1-5 or empty)

Note what is NOT here: there is no "sla_breached" column. A real help desk export
rarely gives you that. In Phase 2 you will calculate it yourself from
first_response_at, created_at, and the SLA targets in config.py.

THE STORY THE DATA TELLS:
    - Bigger and riskier accounts file more tickets, and more urgent ones.
    - Accounts heading toward churn file even more tickets.
    - Riskier accounts wait longer for a first response, so they breach SLA more.
    - CSAT (satisfaction score) drops after a breach and for unhappy accounts.
      Only ~45% of customers answer the survey, so many csat values are empty.

MESSY DATA ON PURPOSE: about 2% of tickets appear twice, an older "open" copy and
the newer "resolved" copy, as if the export caught them mid-update. Cleaning keeps
the row with the latest updated_at.
"""

import numpy as np
import pandas as pd

import config

CATEGORIES = np.array(["Bug", "How-to", "Integration", "Billing", "Performance", "Access"])
# Typical hours from creation to resolution, by priority (before risk slows things down).
RESOLUTION_HOURS = {"P1": 6, "P2": 24, "P3": 72}


def main() -> None:
    rng = np.random.default_rng(config.SEED + 3)
    state = pd.read_parquet(config.TRUTH_DIR / "account_month_state.parquet")
    data_end = pd.Timestamp(config.TELEMETRY_END) + pd.Timedelta(days=1)

    # --- 1) How many tickets each account files each month --------------
    r = state["term_risk"].to_numpy()
    lam = (0.12 + 0.006 * state["seats"].to_numpy()) * (1 + 1.5 * r)
    lam = np.where(state["in_decline"].to_numpy(), lam * 1.6, lam)
    n_tickets = rng.poisson(lam)

    # One row per ticket, carrying its account-month's details.
    t = state.loc[np.repeat(state.index.to_numpy(), n_tickets)].reset_index(drop=True)
    n = len(t)
    r = t["term_risk"].to_numpy()

    # --- 2) Priority: risky accounts have more P1/P2 emergencies ---------
    p1 = 0.04 + 0.06 * r
    p2 = 0.18 + 0.12 * r
    roll = rng.random(n)
    priority = np.where(roll < p1, "P1", np.where(roll < p1 + p2, "P2", "P3"))
    target = pd.Series(priority).map(config.SLA_TARGET_HOURS).to_numpy()

    # --- 3) Timestamps ---------------------------------------------------
    month = t["month"].dt.to_period("M")
    seconds = month.dt.days_in_month.to_numpy() * 24 * 3600
    created = t["month"] + pd.to_timedelta((rng.random(n) * seconds).astype(int), unit="s")

    # First response time is drawn relative to the SLA target. A healthy account
    # usually hears back in about half the allowed time; a risky one often waits longer.
    response_hours = target * rng.lognormal(np.log(0.55) + 0.9 * r, 0.6)
    first_response = created + pd.to_timedelta(response_hours * 3600, unit="s")

    base = pd.Series(priority).map(RESOLUTION_HOURS).to_numpy()
    resolve_hours = response_hours + base * (1 + r) * rng.lognormal(0, 0.8, size=n)
    resolved = created + pd.to_timedelta(resolve_hours * 3600, unit="s")
    still_open = resolved >= data_end  # not solved by the time our data ends
    resolved = resolved.where(~still_open)  # becomes empty (NaT) for open tickets

    # --- 4) CSAT survey (only for solved tickets, and only some reply) ---
    breached = response_hours > target
    score = (4.6 - 1.3 * breached - 1.6 * r - 0.5 * t["in_decline"].to_numpy()
             + rng.normal(0, 0.6, size=n))
    score = np.clip(np.round(score), 1, 5)
    answered = (rng.random(n) < 0.45) & ~still_open.to_numpy()
    csat = np.where(answered, score, np.nan)

    tickets = pd.DataFrame(
        {
            "ticket_id": [f"TCK-{i + 1:06d}" for i in range(n)],
            "account_id": t["account_id"],
            "priority": priority,
            "category": rng.choice(CATEGORIES, size=n),
            "status": np.where(still_open, "open", "resolved"),
            "created_at": created,
            "first_response_at": first_response,
            "resolved_at": resolved,
            # updated_at = the last time anything changed on the ticket
            "updated_at": resolved.fillna(first_response),
            "csat": csat,
        }
    )
    # Responses that would land after our data ends haven't happened yet.
    late = tickets["first_response_at"] >= data_end
    tickets.loc[late, "first_response_at"] = pd.NaT
    tickets.loc[late, "updated_at"] = tickets.loc[late, "created_at"]

    # --- 5) Messy data: stale "open" copies of some resolved tickets -----
    resolved_rows = tickets[tickets["status"] == "resolved"]
    stale = resolved_rows.sample(frac=config.TICKET_UPDATE_RATE, random_state=config.SEED).copy()
    stale["status"] = "open"
    stale["resolved_at"] = pd.NaT
    stale["csat"] = np.nan
    stale["updated_at"] = stale["first_response_at"]
    tickets = pd.concat([tickets, stale], ignore_index=True).sort_values("created_at", ignore_index=True)

    tickets.to_parquet(config.RAW_DIR / "tickets.parquet", index=False)
    print(f"  tickets:   {tickets['ticket_id'].nunique():,} ({len(stale):,} stale duplicate rows added)")


if __name__ == "__main__":
    main()
