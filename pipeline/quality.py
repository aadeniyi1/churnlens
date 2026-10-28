"""
pipeline/quality.py: data quality checks on the finished warehouse.

Run it with:   uv run run.py build      (checks run automatically after the build)
          or:  uv run run.py check      (checks only)

Every check is a SQL query that counts BAD rows. Zero bad rows = pass.
If any check fails, the script exits with an error code. That matters later:
GitHub Actions treats an error code as a failed job, so bad data stops the nightly
pipeline before it reaches the dashboard.

To add a check, add one line to CHECKS: (description, SQL that counts bad rows).
"""

import sys

import duckdb

import config

CHECKS: list[tuple[str, str]] = [
    # --- Keys are unique ------------------------------------------------------
    ("dim_account.account_id is unique",
     "SELECT count(*) - count(DISTINCT account_id) FROM dim_account"),
    ("fact_contract.contract_id is unique",
     "SELECT count(*) - count(DISTINCT contract_id) FROM fact_contract"),
    ("stg_events.event_id is unique (duplicates removed)",
     "SELECT count(*) - count(DISTINCT event_id) FROM stg_events"),
    ("fact_ticket.ticket_id is unique (stale copies removed)",
     "SELECT count(*) - count(DISTINCT ticket_id) FROM fact_ticket"),
    ("fact_arr_monthly has one row per account per month",
     "SELECT count(*) - count(DISTINCT (account_id, month_start)) FROM fact_arr_monthly"),

    # --- Every fact points to a real account ("no orphans") -------------------
    ("every contract belongs to a known account",
     "SELECT count(*) FROM fact_contract WHERE account_id NOT IN (SELECT account_id FROM dim_account)"),
    ("every ticket belongs to a known account",
     "SELECT count(*) FROM fact_ticket WHERE account_id NOT IN (SELECT account_id FROM dim_account)"),
    ("every usage row belongs to a known account",
     "SELECT count(*) FROM fact_usage_daily WHERE account_id NOT IN (SELECT account_id FROM dim_account)"),
    ("every parent account exists",
     ("SELECT count(*) FROM dim_account WHERE parent_account_id IS NOT NULL "
      "AND parent_account_id NOT IN (SELECT account_id FROM dim_account)")),

    # --- Values make business sense --------------------------------------------
    ("ARR is never negative",
     "SELECT count(*) FROM fact_arr_monthly WHERE arr < 0"),
    ("contracts end after they start",
     "SELECT count(*) FROM fact_contract WHERE end_date <= start_date"),
    ("usage only happens while a contract is active",
     "SELECT count(*) FROM fact_usage_daily WHERE licensed_seats IS NULL"),
    ("daily active users never exceed licensed seats",
     "SELECT count(*) FROM fact_usage_daily WHERE active_users > licensed_seats"),
    ("first response comes after the ticket was created",
     "SELECT count(*) FROM fact_ticket WHERE first_response_at < created_at"),
    ("CSAT is between 1 and 5",
     "SELECT count(*) FROM fact_ticket WHERE csat NOT BETWEEN 1 AND 5"),

    # --- Numbers reconcile ------------------------------------------------------
    ("ARR bridge balances (start + changes = end) every month",
     ("SELECT count(*) FROM mart_arr_bridge WHERE abs(starting_arr + new_arr + expansion_arr "
      "+ contraction_arr + churned_arr - ending_arr) > 0.01")),
    ("every account in the CRM made it into dim_account",
     (f"SELECT (SELECT count(*) FROM read_parquet('{config.RAW_DIR.as_posix()}/accounts.parquet')) "
      "- (SELECT count(*) FROM dim_account)")),
    ("GRR is never above 100%",
     "SELECT count(*) FROM metric_retention_12m WHERE grr > 1"),
]


def run_checks(con: duckdb.DuckDBPyConnection) -> int:
    """Run every check, print a pass/fail line for each, and return the number of failures."""
    failures = 0
    for description, sql in CHECKS:
        bad_rows = con.execute(sql).fetchone()[0]
        if bad_rows == 0:
            print(f"  PASS  {description}")
        else:
            failures += 1
            print(f"  FAIL  {description}  ({bad_rows:,} bad rows)")

    # Not pass/fail, just useful to see: how much mess did cleaning remove?
    raw = config.RAW_DIR.as_posix()
    dup_events = con.execute(
        f"SELECT (SELECT count(*) FROM read_parquet('{raw}/events/*.parquet')) "
        "- (SELECT count(*) FROM stg_events)"
    ).fetchone()[0]
    stale_tickets = con.execute(
        f"SELECT (SELECT count(*) FROM read_parquet('{raw}/tickets.parquet')) "
        "- (SELECT count(*) FROM fact_ticket)"
    ).fetchone()[0]
    print(f"\n  cleaning removed {dup_events:,} duplicate events and {stale_tickets:,} stale ticket rows")
    return failures


def main() -> None:
    if not config.WAREHOUSE_PATH.exists():
        sys.exit("No warehouse found. Run this first:  uv run run.py build")
    con = duckdb.connect(str(config.WAREHOUSE_PATH), read_only=True)
    failures = run_checks(con)
    con.close()
    if failures:
        sys.exit(f"\n  {failures} data quality check(s) failed")
    print(f"  all {len(CHECKS)} checks passed")


if __name__ == "__main__":
    main()
