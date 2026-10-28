"""
tests/test_api.py: checks the API answers correctly and keeps its data locked.

TestClient calls the API in-process, like a browser would, without starting a
server. These tests read your local warehouse, so they are skipped if you
haven't run  uv run run.py all  yet.
"""

import pytest
from fastapi.testclient import TestClient

import config
from api import main

pytestmark = pytest.mark.skipif(not config.WAREHOUSE_PATH.exists(), reason="run `uv run run.py all` first")

KEY = {"X-API-Key": "test-key"}


@pytest.fixture
def client(monkeypatch):
    # Force local DuckDB mode with a known key, whatever your .env says.
    monkeypatch.setenv("CHURNLENS_DB", "duckdb")
    monkeypatch.setenv("API_KEY", "test-key")
    return TestClient(main.app)


def test_status_needs_no_key(client):
    r = client.get("/status")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_data_endpoints_need_the_right_key(client, headers):
    assert client.get("/v1/accounts", headers=headers).status_code == 401


def test_internet_mode_without_a_key_refuses_everything(client, monkeypatch):
    # On Render (postgres mode) a missing API_KEY must never mean "open to all".
    monkeypatch.setenv("CHURNLENS_DB", "postgres")
    monkeypatch.delenv("API_KEY")
    assert client.get("/v1/accounts", headers={"X-API-Key": main.DEV_KEY}).status_code == 503


def test_accounts_are_sorted_and_filtered(client):
    body = client.get("/v1/accounts?segment=SMB&limit=20", headers=KEY).json()
    accounts = body["accounts"]
    assert 0 < len(accounts) <= 20 and body["total"] >= len(accounts)
    assert all(a["segment"] == "SMB" for a in accounts)
    at_risk = [a["arr_at_risk"] for a in accounts]
    assert at_risk == sorted(at_risk, reverse=True)


def test_paging_does_not_repeat_accounts(client):
    page1 = client.get("/v1/accounts?limit=10&offset=0", headers=KEY).json()["accounts"]
    page2 = client.get("/v1/accounts?limit=10&offset=10", headers=KEY).json()["accounts"]
    assert not {a["account_id"] for a in page1} & {a["account_id"] for a in page2}


def test_account_detail_matches_the_list(client):
    top = client.get("/v1/accounts?limit=1", headers=KEY).json()["accounts"][0]
    detail = client.get(f"/v1/accounts/{top['account_id']}", headers=KEY).json()
    assert detail["churn_probability"] == top["churn_probability"]
    assert set(detail["health_components"]) == {"utilization", "usage_trend", "support", "contract"}
    history = client.get(f"/v1/accounts/{top['account_id']}/history", headers=KEY).json()["history"]
    assert history[-1]["month_start"] == detail["scored_month"]


def test_bad_and_unknown_account_ids(client):
    assert client.get("/v1/accounts/not-an-id", headers=KEY).status_code == 422  # wrong format
    assert client.get("/v1/accounts/ACC-99999", headers=KEY).status_code == 404  # valid id, no such account


def test_summary_is_sensible(client):
    s = client.get("/v1/metrics/summary", headers=KEY).json()
    assert s["arr"] > 0 and s["customers"] > 0
    assert 0 < s["grr"] <= 1 and s["grr"] <= s["nrr"]  # GRR can never beat NRR
    assert 0 <= s["arr_at_risk"] <= s["arr"]
