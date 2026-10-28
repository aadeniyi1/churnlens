# Metric definitions

These are the official definitions for every metric in ChurnLens. The SQL, the analysis notebook,
the dashboard, and the business documents all follow this page. When anything disagrees with it,
this page wins and the code gets fixed.

Each entry gives the business question, the formula, where it is calculated, and the edge cases.

---

## Revenue

### ARR (annual recurring revenue)
- **Question:** How much recurring revenue are we contracted to receive over a year, right now?
- **Formula:** Sum of `arr` for every contract active on the **last day of the month**. A contract's ARR is
  `seats × list price per seat per month × 12 × discount`.
- **Where:** `fact_arr_monthly.arr`, rolled up in `mart_arr_bridge.ending_arr`.
- **Edge cases:** One-time fees and services are not ARR (this dataset has none). If a contract ends mid-month,
  it doesn't count in that month. In this dataset every contract ends on a month's last day, so this never happens.

### ARR change types
Each account-month is labeled by comparing its ARR with the previous month:

| Label | Rule |
|---|---|
| `new` | Previous month 0, this month above 0 |
| `expansion` | ARR went up (more seats or a higher plan) |
| `contraction` | ARR went down but is still above 0 |
| `churn` | Previous month above 0, this month 0 |
| `flat` | No change |

### ARR bridge (waterfall)
- **Formula:** `starting ARR + new + expansion + contraction + churn = ending ARR`. Contraction and churn
  are stored as negative numbers.
- **Where:** `mart_arr_bridge`. A data quality check confirms it balances every month.

---

## Retention

### NRR (net revenue retention, 12-month)
- **Question:** Of the revenue we had a year ago, how much do those same customers pay us now?
- **Formula:** `ARR now from customers who were paying 12 months ago ÷ their ARR 12 months ago`.
- **Where:** `metric_retention_12m.nrr`, by segment and overall.
- **Edge cases:** Customers who joined during the 12 months are excluded. Expansion counts, so NRR can be above 100%.
  Above 100% means the existing base grows even with zero new sales.

### GRR (gross revenue retention, 12-month)
- **Question:** Ignoring upsell, how much revenue did we keep?
- **Formula:** `Σ min(ARR now, ARR 12 months ago) ÷ Σ ARR 12 months ago`, over customers paying 12 months ago.
- **Where:** `metric_retention_12m.grr`.
- **Edge cases:** Each customer is capped at its own starting ARR, so one customer's expansion can't hide another's
  churn. GRR is never above 100%, and a data quality check enforces that.

### Logo churn rate
- **Question:** What share of customers did we lose?
- **Formula:** `customers who churned in the period ÷ customers active at the start of the period`.
- **Where:** `mart_arr_bridge.churned_customers` and `customers`. 12-month logo retention =
  `retained_customers ÷ starting_customers` in `metric_retention_12m`.
- **Note:** Logo churn and ARR churn can tell opposite stories. See Question 1 in the analysis notebook.

### Cohort retention
- **Question:** For customers who signed in the same quarter, what share of their starting ARR (and how many of
  them) is still here N months later?
- **Formula:** `ARR at month N from the cohort ÷ the cohort's ARR in its first month`. Logo retention works
  the same way with customer counts.
- **Where:** `mart_cohort_retention`.
- **Edge cases:** A cohort only gets a row for month N once every member has reached month N, so recent cohorts
  aren't shown as falsely perfect.

---

## Product usage

### Monthly active users (MAU)
- **Formula:** Distinct `user_id`s with at least one event in the calendar month, per account.
- **Where:** `mart_account_month.monthly_active_users`.
- **Edge cases:** Never add up daily active users to get MAU, because one person active on 10 days would count 10 times.

### Seat utilization (license utilization)
- **Question:** Are customers using what they pay for?
- **Formula:** `monthly active users ÷ licensed seats`.
- **Where:** `mart_account_month.seat_utilization`.
- **Thresholds used in analysis:** under 40% = high risk, 40–55% = watch, 55% and above = healthy.
  Customers under 40% in their first 90 days churn at their first renewal about twice as often as customers above 70%.

### Key feature adoption
- **Formula:** Events of the "sticky" features (`dashboard_created`, `integration_sync`) per month.
  Customers who build dashboards and connect integrations are harder to replace.
- **Where:** `mart_account_month.key_feature_events`, `fact_usage_daily.key_feature_events`.

---

## Support

### SLA attainment and breach
- **Question:** Do we answer customers as fast as we promised?
- **First-response targets:** P1 = 1 hour, P2 = 4 hours, P3 = 24 hours (`config.SLA_TARGET_HOURS`).
- **Formula:** A ticket **breaches** when `first_response_at − created_at` is longer than its target.
  SLA attainment = `tickets not breached ÷ tickets with a first response`.
- **Where:** `fact_ticket.sla_breached`, `mart_account_month.sla_breaches`.
- **Edge cases:** Tickets with no response yet have `sla_breached` = empty and are left out of the rate.
  Hours are calendar hours, not business hours.

### CSAT (customer satisfaction)
- **Formula (score):** Average of 1–5 survey answers. **Formula (CSAT %):** share of answers that are 4 or 5.
- **Where:** `fact_ticket.csat`, `mart_account_month.avg_csat`.
- **Edge cases:** Only about 45% of solved tickets get a survey answer. Unanswered surveys are empty and excluded,
  never counted as 0.

---

## Account health and churn (Phase 4)

### Health score
A 0–100 score built from four weighted parts: usage trend 35%, seat utilization 25%,
support experience (SLA and CSAT) 25%, contract signals 15%. Tiers: **Healthy** ≥ 70, **Watch** 40–69,
**At risk** < 40. Full definition arrives with Phase 4.

### Churn probability
The model's estimated chance that an account does not renew at its next renewal date. It is scored using
only data available **90 days before renewal**, so the result can be acted on and doesn't leak future information.
