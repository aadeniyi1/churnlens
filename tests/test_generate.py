"""
tests/test_generate.py: checks that the generator produces sensible data.

Run with:  uv run pytest

These tests generate a SMALL dataset (200 accounts) into a temporary folder, so
they run in a few seconds and never touch your real data/ folder.
"""

import pandas as pd
import pytest

import config
from generate import accounts, contracts, tickets, usage


@pytest.fixture(scope="module")
def raw_dir(tmp_path_factory):
    # Point every path in config.py at a throwaway folder, then generate.
    tmp = tmp_path_factory.mktemp("raw")
    mp = pytest.MonkeyPatch()
    mp.setattr(config, "N_ACCOUNTS", 200)
    mp.setattr(config, "RAW_DIR", tmp)
    mp.setattr(config, "EVENTS_DIR", tmp / "events")
    mp.setattr(config, "TRUTH_DIR", tmp / "_truth")
    for module in (accounts, contracts, usage, tickets):
        module.main()
    yield tmp
    mp.undo()


def test_account_ids_are_unique(raw_dir):
    acc = pd.read_parquet(raw_dir / "accounts.parquet")
    assert len(acc) == 200
    assert acc["account_id"].is_unique


def test_parents_exist(raw_dir):
    acc = pd.read_parquet(raw_dir / "accounts.parquet")
    parents = acc["parent_account_id"].dropna()
    assert parents.isin(acc["account_id"]).all()


def test_contracts_are_valid(raw_dir):
    con = pd.read_parquet(raw_dir / "contracts.parquet")
    assert con["contract_id"].is_unique
    assert (con["arr"] > 0).all()
    assert (pd.to_datetime(con["end_date"]) > pd.to_datetime(con["start_date"])).all()
    allowed = {"renewed", "expanded", "contracted", "churned", "open"}
    assert set(con["renewal_outcome"]) <= allowed


def test_risky_accounts_churn_more(raw_dir):
    # The whole project depends on this pattern existing in the data.
    con = pd.read_parquet(raw_dir / "contracts.parquet")
    risk = pd.read_parquet(raw_dir / "_truth" / "contract_truth.parquet")
    df = con.merge(risk, on="contract_id")
    decided = df[df["renewal_outcome"] != "open"]
    high = decided[decided["term_risk"] > 0.4]["renewal_outcome"].eq("churned").mean()
    low = decided[decided["term_risk"] < 0.2]["renewal_outcome"].eq("churned").mean()
    assert high > low


def test_events_exist_for_every_month(raw_dir):
    files = sorted((raw_dir / "events").glob("events_*.parquet"))
    months = pd.period_range(config.TELEMETRY_START, config.TELEMETRY_END, freq="M")
    assert len(files) == len(months)


def test_tickets_have_valid_priorities(raw_dir):
    t = pd.read_parquet(raw_dir / "tickets.parquet")
    assert set(t["priority"]) <= set(config.SLA_TARGET_HOURS)
    assert t["csat"].dropna().between(1, 5).all()
