"""
examples/client.py: a sample program that uses the ChurnLens API, the way a
customer's own system would.

It does what a "nightly CRM sync" job does:
    1. prints the headline numbers,
    2. lists the riskiest accounts renewing in the next 3 months,
    3. downloads every account's score (page by page) and saves a CSV that a
       CRM like Salesforce or HubSpot could import.

It uses only Python's standard library (no pip installs), so anyone can run it.

RUN IT
    Against your laptop (start the API first in another terminal: uv run run.py api)
        uv run examples/client.py

    Against the live API on Render
        Mac:     export CHURNLENS_API_URL=https://YOUR-APP.onrender.com
                 export CHURNLENS_API_KEY=your-key
                 uv run examples/client.py
        Windows: $env:CHURNLENS_API_URL="https://YOUR-APP.onrender.com"; $env:CHURNLENS_API_KEY="your-key"
                 uv run examples/client.py
"""

import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_URL = os.environ.get("CHURNLENS_API_URL", "http://127.0.0.1:8000").rstrip("/")
API_KEY = os.environ.get("CHURNLENS_API_KEY", "dev-key")
OUTPUT = Path(__file__).resolve().parent / "crm_sync.csv"


def get(path: str, **params) -> dict | list:
    """GET one endpoint and return the JSON. Retries while a sleeping server wakes up."""
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{BASE_URL}{path}" + (f"?{query}" if query else "")
    request = urllib.request.Request(url, headers={"X-API-Key": API_KEY})

    # Render's free plan puts the API to sleep after 15 idle minutes. The first
    # request then takes up to a minute while it wakes, so we wait and retry.
    for attempt in range(1, 5):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.load(response)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                sys.exit("401: the API key was refused. Check CHURNLENS_API_KEY.")
            if e.code in (502, 503, 504) and attempt < 4:
                print(f"  server is waking up (HTTP {e.code}), retrying in 10s...")
                time.sleep(10)
                continue
            sys.exit(f"HTTP {e.code} from {url}: {e.read().decode()[:300]}")
        except urllib.error.URLError as e:
            sys.exit(f"Could not reach {BASE_URL} ({e.reason}). Is the API running?")
    sys.exit("The API did not wake up after 4 tries.")


def all_accounts(page_size: int = 500) -> list[dict]:
    """Follow the pages (limit + offset) until every account is downloaded."""
    accounts, offset = [], 0
    while True:
        page = get("/v1/accounts", limit=page_size, offset=offset)
        accounts += page["accounts"]
        offset += page_size
        if offset >= page["total"]:
            return accounts


def main() -> None:
    print(f"ChurnLens API at {BASE_URL}")
    status = get("/status")
    print(f"  status: {status['status']}, data: {status['data_source']}, scores for {status['scored_month']}")

    s = get("/v1/metrics/summary")
    print(f"\nAs of {s['as_of']}: ARR ${s['arr'] / 1e6:.1f}M across {s['customers']:,} customers")
    print(f"  NRR {s['nrr']:.0%} | GRR {s['grr']:.0%} | ARR at risk ${s['arr_at_risk'] / 1e6:.1f}M "
          f"({s['high_risk_accounts']} high-risk accounts)")

    urgent = get("/v1/accounts", risk_tier="High", renewing_within_months=3, limit=10)
    print(f"\nHigh-risk accounts renewing within 3 months: {urgent['total']} (top 10 by ARR at risk)")
    for a in urgent["accounts"]:
        reason = (a["reasons"] or ["-"])[0]
        print(f"  {a['account_id']}  {a['account_name'][:28]:<28} {a['segment']:<11} "
              f"${a['arr_at_risk']:>9,.0f} at risk  ({a['churn_probability']:.0%})  {reason}")

    # The "sync": one row per account, in the columns a CRM import would map to fields.
    rows = all_accounts()
    with OUTPUT.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["account_id", "churn_risk_tier", "churn_probability", "health_score",
                         "arr_at_risk", "months_to_renewal", "top_reason"])
        for a in rows:
            writer.writerow([a["account_id"], a["risk_tier"], a["churn_probability"], a["health_score"],
                             a["arr_at_risk"], a["months_to_renewal"], (a["reasons"] or [""])[0]])
    print(f"\nSaved {len(rows):,} accounts to {OUTPUT}")


if __name__ == "__main__":
    main()
