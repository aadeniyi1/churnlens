"""
pipeline/publish.py: copies the finished tables from DuckDB to Supabase Postgres.

Run it with:   uv run run.py publish

WHY: DuckDB is a file on your laptop, so the hosted dashboard (and later the API)
can't see it. Supabase gives us a free Postgres database on the internet. We
only send the small, finished tables the dashboard needs, not the 1.7M raw
events, so we stay far inside the free plan.

SETUP (once): put your Supabase connection string in a file called .env:
    SUPABASE_DB_URL=postgresql://postgres.xxxx:PASSWORD@aws-0-xx.pooler.supabase.com:5432/postgres
Use the "Session pooler" string from Supabase (Connect button -> Session pooler).
It works on networks without IPv6, unlike the "Direct connection" string.

HOW: everything happens inside ONE transaction. Either every table is replaced,
or (if anything fails) nothing changes, so the dashboard never sees a half-loaded
database.
"""

import os

import duckdb
import psycopg
from dotenv import load_dotenv

import config

# The tables the dashboard and API read.
TABLES = [
    "dim_account",
    "dim_csm",
    "dim_product",
    "fact_contract",
    "fact_ticket",
    "mart_account_month",
    "mart_arr_bridge",
    "mart_cohort_retention",
    "metric_retention_12m",
    "fact_account_health",
    "model_metrics",
]

# DuckDB type name -> Postgres type name
TYPE_MAP = {
    "VARCHAR": "text",
    "BOOLEAN": "boolean",
    "INTEGER": "integer",
    "BIGINT": "bigint",
    "HUGEINT": "numeric",
    "DOUBLE": "double precision",
    "FLOAT": "real",
    "DATE": "date",
    "TIMESTAMP": "timestamp",
    "TIMESTAMP_NS": "timestamp",
    "TIMESTAMP WITH TIME ZONE": "timestamptz",
}


def pg_type(duck_type: str) -> str:
    if duck_type.startswith("DECIMAL"):
        return "numeric"
    return TYPE_MAP.get(duck_type, "text")


def copy_table(duck: duckdb.DuckDBPyConnection, cur: psycopg.Cursor, table: str) -> int:
    """Re-create one table in Postgres and stream its rows in with COPY (the fast bulk loader)."""
    columns = duck.execute(f"DESCRIBE {table}").fetchall()  # (name, type, ...)
    col_defs = ", ".join(f'"{name}" {pg_type(dtype)}' for name, dtype, *_ in columns)
    col_names = ", ".join(f'"{name}"' for name, *_ in columns)

    cur.execute(f'DROP TABLE IF EXISTS "{table}"')
    cur.execute(f'CREATE TABLE "{table}" ({col_defs})')

    rows = duck.execute(f"SELECT * FROM {table}").fetchall()
    with cur.copy(f'COPY "{table}" ({col_names}) FROM STDIN') as copy:
        for row in rows:
            copy.write_row(row)
    return len(rows)


def main() -> None:
    load_dotenv(config.PROJECT_ROOT / ".env")
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise SystemExit("SUPABASE_DB_URL is not set. Copy .env.example to .env and fill it in.")

    duck = duckdb.connect(str(config.WAREHOUSE_PATH), read_only=True)
    missing = [t for t in TABLES if not duck.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [t]).fetchone()[0]]
    if missing:
        raise SystemExit(f"Missing tables {missing}. Run:  uv run run.py all")

    # `with` commits the transaction if everything succeeds, and rolls back on any error.
    with psycopg.connect(url, connect_timeout=15) as pg, pg.cursor() as cur:
        for table in TABLES:
            n = copy_table(duck, cur, table)
            print(f"  {table:<24} {n:>8,} rows")
        # Indexes make the dashboard's most common lookups fast.
        cur.execute('CREATE INDEX ON "fact_account_health" (account_id, month_start)')
        cur.execute('CREATE INDEX ON "mart_account_month" (account_id, month_start)')
        cur.execute('CREATE INDEX ON "fact_ticket" (account_id)')
    duck.close()
    print("  published to Supabase")


if __name__ == "__main__":
    main()
