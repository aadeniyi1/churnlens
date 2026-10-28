# ChurnLens API: integration guide

This guide is for someone connecting another system to ChurnLens, for example a CRM, a data
warehouse job, or a Slack bot. It covers authentication, every endpoint, paging, errors, and three
common integrations.

Interactive docs, where you can try every call in the browser: **`<base URL>/docs`**

| Environment | Base URL | Key |
|---|---|---|
| Your laptop (`uv run run.py api`) | `http://127.0.0.1:8000` | `dev-key`, or `API_KEY` from `.env` |
| Hosted on Render | `https://churnlens-api-bber.onrender.com` ([live docs](https://churnlens-api-bber.onrender.com/docs)) | ask the owner |

All data is synthetic. Scores refresh when the pipeline runs (`uv run run.py all` then `publish`).

---

## 1. Authentication

Send your key in the `X-API-Key` header on every `/v1` request. `/status` needs no key.

```bash
curl -H "X-API-Key: dev-key" http://127.0.0.1:8000/v1/metrics/summary
```

```python
import urllib.request, json
req = urllib.request.Request("http://127.0.0.1:8000/v1/metrics/summary", headers={"X-API-Key": "dev-key"})
print(json.load(urllib.request.urlopen(req)))
```

Keep the key out of code and out of Git. Read it from an environment variable or a secrets manager.

## 2. Endpoints

All endpoints are `GET` and read-only. Money is in US dollars per year. Rates are decimals (`0.93` = 93%).

| Endpoint | Returns | Typical use |
|---|---|---|
| `/status` | `status`, `data_source`, `scored_month` | Uptime monitor, "how fresh are the scores?" |
| `/v1/accounts` | Current risk for every account, riskiest first | Nightly CRM sync, risk reports |
| `/v1/accounts/{account_id}` | One account: profile, contract, score breakdown, reasons | Account page in a CRM, CSM prep |
| `/v1/accounts/{account_id}/history` | Month-by-month ARR, seat utilization, tickets, health, churn probability | Trend charts |
| `/v1/metrics/summary` | ARR, customers, NRR, GRR, ARR at risk | Exec reporting, Slack digest |
| `/v1/metrics/retention` | Latest 12-month NRR and GRR, total and by segment | Board reporting |
| `/v1/model` | Which model is live and its test results | Model governance, "can we trust this?" |

### Filters and paging on `/v1/accounts`

| Parameter | Values | Default |
|---|---|---|
| `segment` | `SMB`, `Mid-Market`, `Enterprise` | all |
| `risk_tier` | `High`, `Medium`, `Low` | all |
| `renewing_within_months` | 0 to 12 | all |
| `limit` | 1 to 500 | 50 |
| `offset` | rows to skip | 0 |

The response includes `total`, the number of accounts matching the filters. To fetch everything, keep
adding `limit` to `offset` until `offset >= total`. `examples/client.py` shows this.

### Example response: one account from `/v1/accounts`

```json
{
  "account_id": "ACC-02227",
  "account_name": "Richardson Ltd",
  "segment": "Enterprise",
  "region": "North America",
  "csm_name": "Derek Zuniga",
  "arr": 132035.39,
  "churn_probability": 0.5683,
  "risk_tier": "High",
  "arr_at_risk": 75035.71,
  "health_score": 54.7,
  "health_tier": "Watch",
  "months_to_renewal": 5,
  "reasons": ["Usage fell 12 points in 3 months", "50% of recent tickets missed SLA", "Recent CSAT is 3.3 / 5"]
}
```

| Field | Meaning |
|---|---|
| `churn_probability` | Machine-learning model's chance (0 to 1) that the account leaves at its next renewal |
| `risk_tier` | `High` if probability ≥ 0.50, `Medium` if ≥ 0.25, otherwise `Low` |
| `arr_at_risk` | `churn_probability × arr`. Sort by this to decide where to spend time |
| `health_score` | Rule-based score from 0 (worst) to 100, built from usage trend, seat use, support and contract signals |
| `health_tier` | `Healthy` (70+), `Watch` (40 to 69), `At risk` (under 40) |
| `reasons` | Plain-English reasons behind the health score, worst first. Can be empty for healthy accounts |

The two scores are different on purpose. The probability is more accurate; the health score explains
itself. See [model_card.md](model_card.md) for how both were tested.

## 3. Errors

| Code | Meaning | What to do |
|---|---|---|
| 401 | Missing or wrong API key | Check the `X-API-Key` header |
| 404 | No current account with that ID | The account may have churned. Check the ID |
| 422 | A parameter is invalid, e.g. `account_id` isn't like `ACC-01234` or `limit` > 500 | The response body says which parameter |
| 502 / 503 | Server is waking up (free hosting sleeps after 15 idle minutes) or misconfigured | Retry after 10 to 30 seconds |

Errors return JSON like `{"detail": "Missing or wrong API key. Send it in the X-API-Key header."}`.

---

## 4. Common integrations

### A. Nightly CRM sync (Salesforce, HubSpot)

**Goal:** every account record in the CRM shows its churn risk, so account owners see it without opening
another tool.

1. Add custom fields to the Account object: `Churn Risk Tier` (picklist), `Churn Probability` (percent),
   `Health Score` (number), `ARR at Risk` (currency), `Top Churn Reason` (text).
2. Each night, page through `/v1/accounts` and update each CRM account by matching `account_id` to an
   external ID field on the account.
3. `examples/client.py` does the API side of step 2 and writes `examples/crm_sync.csv` with exactly those
   columns. That CSV can be loaded with Salesforce Data Loader or the HubSpot import tool as a first
   version, before automating it.

Run it against the hosted API:

```bash
# macOS / Linux
export CHURNLENS_API_URL=https://churnlens-api-bber.onrender.com
export CHURNLENS_API_KEY=your-key
uv run examples/client.py
```

```powershell
# Windows PowerShell
$env:CHURNLENS_API_URL="https://churnlens-api-bber.onrender.com"
$env:CHURNLENS_API_KEY="your-key"
uv run examples/client.py
```

### B. Monday risk digest in Slack

**Goal:** CS leaders get the accounts that need attention this week, without logging in anywhere.

```
GET /v1/accounts?risk_tier=High&renewing_within_months=3&limit=10
```

Post each account's name, `arr_at_risk`, CSM, and first reason to a channel using a Slack incoming
webhook. A scheduler (GitHub Actions, Zapier, or cron) runs it every Monday at 8am.

### C. Account page widget

**Goal:** a CSM preparing for a call sees the score and why.

Call `/v1/accounts/{account_id}` for the score breakdown and reasons, and
`/v1/accounts/{account_id}/history` to draw a 12-month line of `health_score` and `seat_utilization`.

---

## 5. Limits and good practice

- Scores change at most once per pipeline run (monthly in this demo). Caching responses for an hour or
  more is safe; `/status` → `scored_month` says when they last changed.
- Use `limit=500` when syncing everything: about 5 requests for 2,000 accounts.
- The free hosted API sleeps when idle. Call `/status` first and allow up to a minute for the first reply.
- The API is read-only. Nothing you send can change ChurnLens data.
