"""
pipeline/build.py: builds the DuckDB warehouse from the raw Parquet files.

Run it with:   uv run run.py build

What it does:
    1. Opens (or creates) data/warehouse.duckdb.
    2. Runs every .sql file in pipeline/sql/ in name order. The numbers at the
       front of the file names (01_, 02_ ...) set the order, because later layers
       depend on earlier ones: staging -> dimensions -> facts -> marts -> metrics.
    3. Prints how many rows each table ended up with.

The SQL files contain placeholders like {raw}. render() swaps them for real values
from config.py, so paths and dates are set in exactly one place.
"""

from pathlib import Path

import duckdb
import pandas as pd

import config

SQL_DIR = Path(__file__).parent / "sql"


def placeholders() -> dict[str, str]:
    """The values that replace {name} inside the SQL files."""
    return {
        # as_posix() gives forward slashes, which DuckDB accepts on Windows too
        "{raw}": config.RAW_DIR.as_posix(),
        "{first_month}": pd.Timestamp(config.FIRST_SIGNUP_START).strftime("%Y-%m-01"),
        "{last_month}": pd.Timestamp(config.TELEMETRY_END).strftime("%Y-%m-01"),
        "{telemetry_start}": pd.Timestamp(config.TELEMETRY_START).strftime("%Y-%m-01"),
    }


def render(sql: str) -> str:
    """Fill in the placeholders. Plain text replacement keeps it easy to follow."""
    for key, value in placeholders().items():
        sql = sql.replace(key, value)
    return sql


def run_sql_file(con: duckdb.DuckDBPyConnection, path: Path) -> None:
    # DuckDB can run a whole file of statements separated by semicolons at once.
    con.execute(render(path.read_text()))


def connect(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    """Open the warehouse with a memory cap, so big queries spill to disk instead of crashing."""
    db_path = db_path or config.WAREHOUSE_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute(f"SET memory_limit = '{config.DUCKDB_MEMORY_LIMIT}'")
    return con


def main() -> None:
    if not (config.RAW_DIR / "accounts.parquet").exists():
        raise SystemExit("No raw data found. Run this first:  uv run run.py generate")

    con = connect()
    for path in sorted(SQL_DIR.glob("*.sql")):
        print(f"  running {path.name}")
        run_sql_file(con, path)

    # Show what we built.
    tables = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' ORDER BY 1"
    ).fetchall()
    print()
    for (name,) in tables:
        rows = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
        print(f"  {name:<24} {rows:>12,} rows")
    con.close()
    print(f"\n  warehouse saved to {config.WAREHOUSE_PATH}")


if __name__ == "__main__":
    main()
