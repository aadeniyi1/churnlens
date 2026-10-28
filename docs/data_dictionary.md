# Data dictionary

Every table in `data/warehouse.duckdb`, built by `uv run run.py build`.

The warehouse has four layers. Each one reads only from the layers above it.

| Layer | Prefix | Purpose | Built by |
|---|---|---|---|
| Staging | `stg_` | Clean copies of each raw file: types fixed, duplicates removed | `01_staging.sql` |
| Dimensions | `dim_` | Who and what: accounts, products, CSMs, dates | `02_dimensions.sql` |
| Facts | `fact_` | What happened: contracts, monthly ARR, usage, tickets | `03_facts.sql` |
| Marts and metrics | `mart_`, `metric_` | Analysis-ready tables for the dashboard and model | `04_marts.sql`, `05_metrics.sql` |

**Grain** means what one row represents. Check the grain before summing anything.

---

## Dimensions

### `dim_account`
Grain: one row per customer account.

| Column | Type | Description |
|---|---|---|
| account_id | text | Primary key, e.g. `ACC-00042` |
| account_name | text | Company name |
| parent_account_id | text | Parent company's account_id if this is a subsidiary, otherwise empty |
| parent_account_name | text | Parent company's name |
| ultimate_parent_account_id | text | The top company in the hierarchy (itself if it has no parent). Use this to roll subsidiaries up. |
| child_accounts | int | Number of subsidiaries under this account |
| industry | text | Industry |
| region | text | North America, EMEA, APAC, LATAM |
| segment | text | SMB, Mid-Market, Enterprise |
| employee_band | text | Company size band, e.g. `201-1000` |
| csm_id | text | Customer success manager who owns the account (joins to `dim_csm`) |
| first_contract_date | date | Start of the account's first contract |
| cohort_quarter | text | Quarter of first contract, e.g. `2023-Q1`. Used for cohort retention. |

### `dim_product`
Grain: one row per plan. Columns: `product_id`, `product_name`, `tier` (Starter, Pro, Enterprise), `list_price_per_seat` (US dollars per seat per month).

### `dim_csm`
Grain: one row per customer success manager. Columns: `csm_id`, `csm_name`, `region`, `team` (Commercial or Strategic).

### `dim_date`
Grain: one row per day from 2022-01-01 to 2026-12-31. Columns: `date`, `year`, `quarter`, `month`, `year_month` (`2024-03`), `year_quarter` (`2024-Q1`), `month_start`, `is_month_end`, `day_name`, `is_weekend`.

---

## Facts

### `fact_contract`
Grain: one row per contract (each contract is a 12-month term).

| Column | Type | Description |
|---|---|---|
| contract_id | text | Primary key |
| account_id | text | Joins to `dim_account` |
| product_id | text | Joins to `dim_product` |
| contract_number | int | 1 = first contract, 2 = first renewal, and so on |
| start_date, end_date | date | Contract term. Start is always the 1st of a month. |
| seats | int | Licensed seats |
| arr | decimal | Annual recurring revenue of this contract, after discount |
| renewal_outcome | text | What happened at the end: `renewed`, `expanded`, `contracted`, `churned`, or `open` (still running when the data ends) |
| is_renewal | bool | True for every contract after the first |
| prior_arr | decimal | ARR of the previous contract for the same account |
| arr_change | decimal | `arr - prior_arr` |

### `fact_arr_monthly`
Grain: one row per account per month, from its first contract month until the month after its last contract ends.

| Column | Type | Description |
|---|---|---|
| account_id | text | Joins to `dim_account` |
| month_start | date | First day of the month |
| contract_id, product_id | text | Contract active on the last day of the month |
| licensed_seats | int | Seats on that contract |
| arr | decimal | ARR on the last day of the month (0 in the month after a churn) |
| prev_arr | decimal | ARR the month before |
| arr_change | decimal | `arr - prev_arr` |
| arr_change_type | text | `new`, `expansion`, `contraction`, `churn`, or `flat` |

A churn on a contract ending in the final data month (Dec 2025) shows up in Jan 2026, which is outside the data. Those churns appear in `fact_contract` but not yet in this table.

### `fact_usage_daily`
Grain: one row per account per product per day with at least one event.

| Column | Type | Description |
|---|---|---|
| account_id, product_id | text | Keys |
| date | date | Day of activity |
| events | int | Number of key actions logged |
| active_users | int | Distinct users active that day |
| key_feature_events | int | Events of the "sticky" features: `dashboard_created`, `integration_sync` |
| licensed_seats | int | Seats on the contract active that day |

Do not add up `active_users` across days to get monthly users. One user active on 10 days would be counted 10 times. Use `mart_account_month.monthly_active_users`.

### `fact_ticket`
Grain: one row per support ticket (the latest version of each).

| Column | Type | Description |
|---|---|---|
| ticket_id | text | Primary key |
| account_id | text | Joins to `dim_account` |
| priority | text | P1 (most urgent), P2, P3 |
| category | text | Bug, How-to, Integration, Billing, Performance, Access |
| status | text | `open` or `resolved` |
| created_at, first_response_at, resolved_at | timestamp | Ticket timeline. Empty if it hasn't happened yet. |
| created_date, created_month | date | For joining to `dim_date` and monthly grouping |
| sla_target_hours | int | Allowed hours to first response: P1 1, P2 4, P3 24 |
| first_response_hours | decimal | Hours from creation to first response |
| resolution_hours | decimal | Hours from creation to resolution |
| sla_breached | bool | True if the first response took longer than the target. Empty if there's no response yet. |
| csat | int | Customer satisfaction survey score, 1 to 5. Empty if the customer didn't answer. |

---

## Marts and metrics

### `mart_account_month`
Grain: one row per paying account per month, Jan 2023 to Dec 2025. **This is the main input for the health score and churn model.**

Includes account attributes (`segment`, `region`, `industry`, `csm_id`, `ultimate_parent_account_id`), contract and ARR fields from `fact_arr_monthly`, plus:

| Column | Description |
|---|---|
| monthly_active_users | Distinct users with at least one event in the month |
| events, key_feature_events | Event counts for the month |
| seat_utilization | `monthly_active_users / licensed_seats` |
| tickets, urgent_tickets | Tickets opened in the month (urgent = P1 or P2) |
| sla_breaches | Tickets in the month that missed the first-response SLA |
| csat_responses, avg_csat | Survey responses and their average score |
| contract_end_date | End of the current contract |
| months_to_renewal | Months left on the contract, counting this one (12 down to 1) |
| tenure_months | Months since the account's first contract |

### `mart_arr_bridge`
Grain: one row per month. The ARR waterfall:
`starting_arr + new_arr + expansion_arr + contraction_arr + churned_arr = ending_arr`.
Contraction and churn are negative. Also includes `customers` and `churned_customers`.

### `mart_cohort_retention`
Grain: one row per cohort quarter, segment, and months since start. Columns: `cohort_accounts`, `cohort_starting_arr`, `retained_accounts`, `retained_arr`, `logo_retention`, `arr_retention`. A cohort only gets rows for months that every one of its members has reached.

### `metric_retention_12m`
Grain: one row per month per segment, plus an `All` row for each month.

| Column | Description |
|---|---|
| starting_customers, starting_arr | Accounts paying 12 months earlier, and their ARR then |
| retained_customers, ending_arr | How many of them still pay now, and their ARR now |
| nrr | Net revenue retention: `ending_arr / starting_arr` |
| grr | Gross revenue retention: each account's current ARR capped at its starting ARR, summed, divided by `starting_arr` |

Customers who joined during the 12 months are excluded on purpose. Full definitions are in `docs/metrics.md` (Phase 3).
