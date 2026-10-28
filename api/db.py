"""
api/db.py: the ONLY place the API talks to a database.

Two modes, picked by the CHURNLENS_DB setting:
    duckdb   (default) reads data/warehouse.duckdb on your laptop. No setup needed.
    postgres reads Supabase, using SUPABASE_DB_URL. Render sets this mode for you
             (see render.yaml), and you can try it locally with:
                 Mac:     CHURNLENS_DB=postgres uv run run.py api
                 Windows: $env:CHURNLENS_DB="postgres"; uv run run.py api

Every endpoint calls fetch_all("SELECT ... WHERE x = ?", (value,)). Writing the
parameters as ? (never pasting values into the SQL string yourself) stops SQL
injection: the database treats the value as data, not as code.
"""

import os
from functools import lru_cache

from dotenv import load_dotenv

import config

load_dotenv(config.PROJECT_ROOT / ".env")  # read .env if there is one (API_KEY, SUPABASE_DB_URL)


def mode() -> str:
    return os.environ.get("CHURNLENS_DB", "duckdb").lower()


def source_name() -> str:
    return "Supabase Postgres" if mode() == "postgres" else "local DuckDB warehouse"


@lru_cache(maxsize=1)
def _pg_pool():
    """A small pool of open Postgres connections, created on first use.

    Opening a brand-new connection to Supabase takes a few hundred milliseconds.
    A pool keeps a couple of connections open and lends them out, so most requests
    skip that wait. max_size=3 keeps us far below the free plan's connection limit.
    """
    from psycopg_pool import ConnectionPool

    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError("CHURNLENS_DB=postgres but SUPABASE_DB_URL is not set")
    return ConnectionPool(url, min_size=0, max_size=3, kwargs={"connect_timeout": 15}, open=True)


def fetch_all(sql: str, params: tuple = ()) -> list[dict]:
    """Run a query and return a list of rows, each row a dict of {column: value}."""
    if mode() == "postgres":
        with _pg_pool().connection() as conn, conn.cursor() as cur:
            cur.execute(sql.replace("?", "%s"), params or None)  # Postgres writes parameters as %s
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    import duckdb

    if not config.WAREHOUSE_PATH.exists():
        raise RuntimeError("No warehouse found. In a terminal, run:  uv run run.py all")
    # read_only=True means the API can never change your data, and it can run
    # at the same time as the dashboard.
    with duckdb.connect(str(config.WAREHOUSE_PATH), read_only=True) as con:
        cur = con.execute(sql, list(params))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_one(sql: str, params: tuple = ()) -> dict | None:
    rows = fetch_all(sql, params)
    return rows[0] if rows else None
