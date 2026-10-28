"""
api/main.py: the ChurnLens REST API.

Run it on your laptop with:   uv run run.py api
Then open http://127.0.0.1:8000/docs for interactive docs where you can try
every endpoint in the browser (click "Authorize" and paste your API key first).

WHAT IT IS FOR
The dashboard is for people. The API is for other software: a CRM like
Salesforce or HubSpot could call it every night to put each account's churn
risk on the account record, or a Slack bot could post the week's riskiest
accounts. docs/api_integration.md walks through those examples.

ENDPOINTS (all read-only)
    GET /status                          is the API up? (no key needed)
    GET /v1/accounts                     current risk for every account, with filters
    GET /v1/accounts/{account_id}        one account in full: profile, contract, score breakdown
    GET /v1/accounts/{account_id}/history  month-by-month health for one account
    GET /v1/metrics/summary              ARR, customers, NRR, GRR, ARR at risk
    GET /v1/metrics/retention            latest 12-month NRR and GRR by segment
    GET /v1/model                        how the churn model was tested

SECURITY
Every /v1 endpoint needs the header  X-API-Key: <your key>.  The key lives in
the API_KEY setting (.env on your laptop, an environment variable on Render),
never in the code.
"""

import json
import os
import secrets

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

from api import db
from api.schemas import (
    AccountDetail,
    AccountHistory,
    AccountList,
    ModelInfo,
    SegmentRetention,
    Status,
    Summary,
)

DEV_KEY = "dev-key"  # only accepted on your laptop, when no API_KEY is set

app = FastAPI(
    title="ChurnLens API",
    version="1.0.0",
    description=(
        "Churn risk, health scores and retention metrics for B2B SaaS accounts. "
        "All data is synthetic. Send your key in the `X-API-Key` header."
    ),
)

# CORS lets a web page on another site (say, an internal tool) call this API from
# the browser. Only GET is allowed, because the API never changes anything.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["X-API-Key"])

# --------------------------------------------------------------------------
# API key check
# --------------------------------------------------------------------------
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def expected_key() -> str:
    key = os.environ.get("API_KEY", "")
    if key and key != "change-me":
        return key
    if db.mode() == "postgres":
        # On the internet with no real key set: refuse everything rather than run unprotected.
        raise HTTPException(503, "Server is missing its API_KEY setting")
    return DEV_KEY


def require_key(key: str | None = Security(api_key_header)) -> None:
    # compare_digest takes the same time whether the first or last character is
    # wrong, so an attacker can't guess the key one character at a time by timing.
    if not key or not secrets.compare_digest(key, expected_key()):
        raise HTTPException(401, "Missing or wrong API key. Send it in the X-API-Key header.")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
ACCOUNT_ID = Path(pattern=r"^ACC-\d{5}$", examples=["ACC-01314"], description="Account ID, e.g. ACC-01314")

# The columns the Risk List shows, and where they come from. Shared by two endpoints.
RISK_COLUMNS = """
    h.account_id, a.account_name, a.segment, a.region, c.csm_name,
    h.arr, h.churn_probability, h.risk_tier, h.arr_at_risk,
    h.health_score, h.health_tier, h.months_to_renewal, h.top_reasons
"""
RISK_JOINS = """
    FROM fact_account_health h
    JOIN dim_account a ON a.account_id = h.account_id
    LEFT JOIN dim_csm c ON c.csm_id = a.csm_id
"""
LATEST = "WHERE h.is_latest"  # only the newest month's score for each account


def split_reasons(row: dict) -> dict:
    """The warehouse stores reasons as 'a | b | c'. The API returns a proper list."""
    text = row.pop("top_reasons", None) or ""
    row["reasons"] = [r.strip() for r in text.split("|") if r.strip()]
    return row


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------
@app.get("/status", response_model=Status, tags=["status"])
def status() -> dict:
    """Health check for uptime monitors. Needs no API key."""
    row = db.fetch_one("SELECT CAST(max(month_start) AS DATE) AS scored_month FROM fact_account_health")
    return {"status": "ok", "data_source": db.source_name(), "scored_month": row["scored_month"]}


@app.get("/v1/accounts", response_model=AccountList, tags=["accounts"], dependencies=[Depends(require_key)])
def list_accounts(
    segment: str | None = Query(None, pattern="^(SMB|Mid-Market|Enterprise)$"),
    risk_tier: str | None = Query(None, pattern="^(High|Medium|Low)$"),
    renewing_within_months: int | None = Query(None, ge=0, le=12),
    limit: int = Query(50, ge=1, le=500, description="Rows per page (max 500)"),
    offset: int = Query(0, ge=0, description="Rows to skip, for paging"),
) -> dict:
    """Every current account, riskiest (most ARR at risk) first. Filters are optional."""
    where, params = "", []
    if segment:
        where += " AND a.segment = ?"
        params.append(segment)
    if risk_tier:
        where += " AND h.risk_tier = ?"
        params.append(risk_tier)
    if renewing_within_months is not None:
        where += " AND h.months_to_renewal <= ?"
        params.append(renewing_within_months)

    total = db.fetch_one(f"SELECT count(*) AS n {RISK_JOINS} {LATEST} {where}", tuple(params))["n"]
    rows = db.fetch_all(
        f"SELECT {RISK_COLUMNS} {RISK_JOINS} {LATEST} {where} "
        "ORDER BY h.arr_at_risk DESC, h.account_id LIMIT ? OFFSET ?",
        (*params, limit, offset),
    )
    return {"total": total, "limit": limit, "offset": offset, "accounts": [split_reasons(r) for r in rows]}


@app.get("/v1/accounts/{account_id}", response_model=AccountDetail, tags=["accounts"],
         dependencies=[Depends(require_key)])
def get_account(account_id: str = ACCOUNT_ID) -> dict:
    """One account in full: who it is, its current contract, and how its scores were built."""
    row = db.fetch_one(
        f"""SELECT {RISK_COLUMNS},
                a.industry, a.employee_band, a.parent_account_id, a.ultimate_parent_account_id,
                a.first_contract_date, CAST(h.month_start AS DATE) AS scored_month, h.model_version,
                h.utilization_score, h.usage_trend_score, h.support_score, h.contract_score,
                k.contract_id, k.product_id, k.start_date, k.end_date, k.seats, k.arr AS contract_arr
            {RISK_JOINS}
            LEFT JOIN fact_contract k ON k.contract_id = h.contract_id
            {LATEST} AND h.account_id = ?""",
        (account_id,),
    )
    if row is None:
        raise HTTPException(404, f"No current account with id {account_id}")

    row["health_components"] = {
        "utilization": row.pop("utilization_score"),
        "usage_trend": row.pop("usage_trend_score"),
        "support": row.pop("support_score"),
        "contract": row.pop("contract_score"),
    }
    contract = {k: row.pop(k) for k in ["contract_id", "product_id", "start_date", "end_date", "seats"]}
    contract["arr"] = row.pop("contract_arr")
    row["current_contract"] = contract if contract["contract_id"] else None
    return split_reasons(row)


@app.get("/v1/accounts/{account_id}/history", response_model=AccountHistory, tags=["accounts"],
         dependencies=[Depends(require_key)])
def get_account_history(account_id: str = ACCOUNT_ID) -> dict:
    """Month-by-month ARR, usage and risk for one account, oldest first. Good for charts."""
    rows = db.fetch_all(
        """SELECT CAST(h.month_start AS DATE) AS month_start, h.arr, m.seat_utilization, m.tickets,
                  h.health_score, h.churn_probability, h.risk_tier
           FROM fact_account_health h
           LEFT JOIN mart_account_month m
                  ON m.account_id = h.account_id AND m.month_start = CAST(h.month_start AS DATE)
           WHERE h.account_id = ?
           ORDER BY h.month_start""",
        (account_id,),
    )
    if not rows:
        raise HTTPException(404, f"No history for account {account_id}")
    return {"account_id": account_id, "history": rows}


@app.get("/v1/metrics/summary", response_model=Summary, tags=["metrics"], dependencies=[Depends(require_key)])
def get_summary() -> dict:
    """The executive numbers from the dashboard's Home page, for the latest month."""
    bridge = db.fetch_one(
        "SELECT month_start, ending_arr, customers FROM mart_arr_bridge ORDER BY month_start DESC LIMIT 1")
    ret = db.fetch_one(
        "SELECT nrr, grr FROM metric_retention_12m WHERE segment = 'All' ORDER BY month_start DESC LIMIT 1")
    risk = db.fetch_one(
        "SELECT round(CAST(sum(arr_at_risk) AS NUMERIC), 2) AS arr_at_risk, "
        "sum(CASE WHEN risk_tier = 'High' THEN 1 ELSE 0 END) AS high_risk_accounts "
        "FROM fact_account_health WHERE is_latest")
    return {
        "as_of": bridge["month_start"],
        "arr": round(bridge["ending_arr"], 2),
        "customers": bridge["customers"],
        **ret,
        **risk,
    }


@app.get("/v1/metrics/retention", response_model=list[SegmentRetention], tags=["metrics"],
         dependencies=[Depends(require_key)])
def get_retention() -> list[dict]:
    """Latest 12-month NRR and GRR, for all customers and for each segment."""
    return db.fetch_all(
        """SELECT segment, month_start, starting_customers, retained_customers,
                  starting_arr, ending_arr, nrr, grr
           FROM metric_retention_12m
           WHERE month_start = (SELECT max(month_start) FROM metric_retention_12m)
           ORDER BY CASE segment WHEN 'All' THEN 0 ELSE 1 END, segment"""
    )


@app.get("/v1/model", response_model=ModelInfo, tags=["model"], dependencies=[Depends(require_key)])
def get_model_info() -> dict:
    """Which model is in use and how well it did on renewals it never saw while training."""
    row = db.fetch_one("SELECT metrics_json FROM model_metrics")
    if row is None:
        raise HTTPException(404, "No model metrics yet. Run:  uv run run.py model")
    return json.loads(row["metrics_json"])
