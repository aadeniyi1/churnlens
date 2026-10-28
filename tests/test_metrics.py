"""
tests/test_metrics.py: proves the NRR and GRR SQL gives the right answer.

We build a tiny made-up dataset where the answer can be worked out by hand,
run the real 05_metrics.sql on it, and compare.

The story (ARR in dollars):
    account   segment      Jan 2024   Jan 2025   what happened
    A         SMB             100        150     expanded
    B         SMB             100          0     churned
    C         Enterprise      200        150     contracted
    D         SMB               -        500     new in 2025, so NOT counted

    Starting ARR (Jan 2024)            = 100 + 100 + 200        = 400
    NRR = ARR now / ARR then           = (150 + 0 + 150) / 400  = 0.75
    GRR = capped ARR now / ARR then    = (100 + 0 + 150) / 400  = 0.625
          (A's 150 is capped at its starting 100, because GRR ignores expansion)
"""

import duckdb
import pytest

from pipeline.build import SQL_DIR, render


@pytest.fixture
def retention():
    con = duckdb.connect()  # in-memory: nothing touches your real warehouse
    con.execute("""
        CREATE TABLE dim_account AS SELECT * FROM (VALUES
            ('A', 'SMB'), ('B', 'SMB'), ('C', 'Enterprise'), ('D', 'SMB')
        ) AS t(account_id, segment);

        CREATE TABLE fact_arr_monthly AS SELECT account_id, CAST(month_start AS DATE) AS month_start, arr
        FROM (VALUES
            ('A', '2024-01-01', 100.0), ('A', '2025-01-01', 150.0),
            ('B', '2024-01-01', 100.0), ('B', '2024-02-01',   0.0),
            ('C', '2024-01-01', 200.0), ('C', '2025-01-01', 150.0),
            ('D', '2025-01-01', 500.0)
        ) AS t(account_id, month_start, arr);
    """)
    con.execute(render((SQL_DIR / "05_metrics.sql").read_text()))
    yield con
    con.close()


def get(con, segment):
    return con.execute(
        "SELECT starting_customers, retained_customers, starting_arr, nrr, grr "
        "FROM metric_retention_12m WHERE month_start = DATE '2025-01-01' AND segment = ?",
        [segment],
    ).fetchone()


def test_overall_nrr_and_grr(retention):
    starting_customers, retained, starting_arr, nrr, grr = get(retention, "All")
    assert starting_customers == 3  # D is new, so it is left out
    assert retained == 2  # B churned
    assert starting_arr == 400
    assert nrr == pytest.approx(0.75)
    assert grr == pytest.approx(0.625)


def test_segment_nrr_and_grr(retention):
    # SMB only: A and B.  NRR = 150 / 200 = 0.75   GRR = 100 / 200 = 0.5
    _, _, starting_arr, nrr, grr = get(retention, "SMB")
    assert starting_arr == 200
    assert nrr == pytest.approx(0.75)
    assert grr == pytest.approx(0.5)


def test_grr_never_exceeds_nrr(retention):
    rows = retention.execute("SELECT nrr, grr FROM metric_retention_12m").fetchall()
    assert all(grr <= nrr for nrr, grr in rows)
