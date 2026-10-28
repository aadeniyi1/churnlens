"""
run.py: the single entry point for the whole project.

Usage (from the project folder):
    uv run run.py generate     # Phase 1: create the synthetic source data
    uv run run.py summary      # print a quick look at what was generated
    uv run run.py build        # Phase 2: build the DuckDB warehouse   (coming next)
    uv run run.py all          # every step that exists so far, in order

Why a Python script instead of a Makefile? `make` is not installed on Windows by
default, and this project has to run on both your Mac and the ThinkPad.
"""

import argparse
import sys
import time

import config


def step(name, func) -> None:
    """Run one step, timing it and printing a clear header."""
    print(f"\n==> {name}")
    t0 = time.perf_counter()
    func()
    print(f"    done in {time.perf_counter() - t0:.1f}s")


def generate() -> None:
    # Imported here (not at the top) so `run.py summary` works even before the
    # generate scripts have been touched, and so each step loads only what it needs.
    from generate import accounts, contracts, tickets, usage

    print(f"Generating data for {config.N_ACCOUNTS:,} accounts (seed {config.SEED})")
    step("1/4 accounts, CSMs, products", accounts.main)
    step("2/4 contracts and renewals", contracts.main)
    step("3/4 product usage events (month by month)", usage.main)
    step("4/4 support tickets", tickets.main)
    print(f"\nAll raw files are in {config.RAW_DIR}")


def summary() -> None:
    """Use DuckDB to peek at the raw Parquet files without loading them into pandas."""
    import duckdb

    raw = config.RAW_DIR.as_posix()  # forward slashes work in DuckDB on Windows too
    if not (config.RAW_DIR / "accounts.parquet").exists():
        sys.exit("No data yet. Run:  uv run run.py generate")

    con = duckdb.connect()  # an in-memory database, nothing is saved
    con.execute(f"SET memory_limit = '{config.DUCKDB_MEMORY_LIMIT}'")
    queries = {
        "Accounts by segment": f"""
            SELECT segment, count(*) AS accounts
            FROM '{raw}/accounts.parquet' GROUP BY 1 ORDER BY 2 DESC""",
        "Renewal outcomes": f"""
            SELECT renewal_outcome, count(*) AS contracts, round(sum(arr)) AS arr
            FROM '{raw}/contracts.parquet' GROUP BY 1 ORDER BY 2 DESC""",
        "Events by type": f"""
            SELECT event_type, count(*) AS events
            FROM '{raw}/events/*.parquet' GROUP BY 1 ORDER BY 2 DESC""",
        "Tickets by priority": f"""
            SELECT priority, count(DISTINCT ticket_id) AS tickets, round(avg(csat), 2) AS avg_csat
            FROM '{raw}/tickets.parquet' GROUP BY 1 ORDER BY 1""",
    }
    for title, sql in queries.items():
        print(f"\n{title}")
        con.sql(sql).show()


def not_yet(phase: str):
    def _inner() -> None:
        print(f"This step arrives in {phase}. Nothing to run yet.")
    return _inner


COMMANDS = {
    "generate": generate,
    "summary": summary,
    "build": not_yet("Phase 2 (warehouse and ETL)"),
    "model": not_yet("Phase 4 (health score and churn model)"),
    "publish": not_yet("Phase 4 (Supabase)"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="ChurnLens pipeline")
    parser.add_argument("command", choices=[*COMMANDS, "all"], help="which step to run")
    args = parser.parse_args()

    if args.command == "all":
        generate()
        summary()
    else:
        COMMANDS[args.command]()


if __name__ == "__main__":
    main()
