-- =============================================================================
-- 04_marts.sql: ready-to-use tables for analysis, the model, and the dashboard.
--
-- A "mart" joins facts and dimensions into the exact shape a consumer needs,
-- so the dashboard and model don't each re-write the same joins.
--   mart_account_month      one row per account per month: the heart of the model
--   mart_arr_bridge         one row per month: how ARR moved (new, expansion, ...)
--   mart_cohort_retention   one row per signup cohort per month since signup
-- =============================================================================

-- mart_account_month -------------------------------------------------------------
-- Only months inside the telemetry window, because before it we have no usage.
CREATE OR REPLACE TABLE mart_account_month AS
WITH usage AS (
    SELECT
        account_id,
        event_month                    AS month_start,
        count(*)                       AS events,
        -- Monthly active users must be counted from events, NOT by adding up daily
        -- active users, or a user active on 10 days would be counted 10 times.
        count(DISTINCT user_id)        AS monthly_active_users,
        count(*) FILTER (WHERE event_type IN ('dashboard_created', 'integration_sync'))
                                       AS key_feature_events
    FROM stg_events
    GROUP BY account_id, event_month
),
support AS (
    SELECT
        account_id,
        created_month                                   AS month_start,
        count(*)                                        AS tickets,
        count(*) FILTER (WHERE priority IN ('P1', 'P2')) AS urgent_tickets,
        count(*) FILTER (WHERE sla_breached)            AS sla_breaches,
        count(csat)                                     AS csat_responses,
        avg(csat)                                       AS avg_csat
    FROM stg_tickets
    GROUP BY account_id, created_month
)
SELECT
    f.account_id,
    f.month_start,
    a.segment,
    a.region,
    a.industry,
    a.csm_id,
    a.ultimate_parent_account_id,
    f.contract_id,
    f.product_id,
    f.arr,
    f.arr_change,
    f.arr_change_type,
    f.licensed_seats,
    coalesce(u.monthly_active_users, 0)                         AS monthly_active_users,
    coalesce(u.events, 0)                                       AS events,
    coalesce(u.key_feature_events, 0)                           AS key_feature_events,
    round(coalesce(u.monthly_active_users, 0) / nullif(f.licensed_seats, 0), 4) AS seat_utilization,
    coalesce(s.tickets, 0)                                      AS tickets,
    coalesce(s.urgent_tickets, 0)                               AS urgent_tickets,
    coalesce(s.sla_breaches, 0)                                 AS sla_breaches,
    coalesce(s.csat_responses, 0)                               AS csat_responses,
    round(s.avg_csat, 2)                                        AS avg_csat,
    c.end_date                                                  AS contract_end_date,
    date_diff('month', f.month_start, c.end_date) + 1           AS months_to_renewal,
    date_diff('month', CAST(date_trunc('month', a.first_contract_date) AS DATE), f.month_start)
                                                                AS tenure_months
FROM fact_arr_monthly f
JOIN dim_account a        ON a.account_id = f.account_id
LEFT JOIN stg_contracts c ON c.contract_id = f.contract_id
LEFT JOIN usage u         ON u.account_id = f.account_id AND u.month_start = f.month_start
LEFT JOIN support s       ON s.account_id = f.account_id AND s.month_start = f.month_start
WHERE f.month_start >= DATE '{telemetry_start}'
  AND f.arr > 0;  -- churn rows (ARR = 0) live in fact_arr_monthly, not here

-- mart_arr_bridge ----------------------------------------------------------------
-- The classic SaaS "ARR waterfall": start + new + expansion - contraction - churn = end.
-- Contraction and churn are stored as negative numbers so the columns add up.
CREATE OR REPLACE TABLE mart_arr_bridge AS
SELECT
    month_start,
    sum(prev_arr)                                              AS starting_arr,
    coalesce(sum(arr_change) FILTER (WHERE arr_change_type = 'new'), 0)         AS new_arr,
    coalesce(sum(arr_change) FILTER (WHERE arr_change_type = 'expansion'), 0)   AS expansion_arr,
    coalesce(sum(arr_change) FILTER (WHERE arr_change_type = 'contraction'), 0) AS contraction_arr,
    coalesce(sum(arr_change) FILTER (WHERE arr_change_type = 'churn'), 0)       AS churned_arr,
    sum(arr)                                                   AS ending_arr,
    count(*) FILTER (WHERE arr > 0)                            AS customers,
    count(*) FILTER (WHERE arr_change_type = 'churn')          AS churned_customers
FROM fact_arr_monthly
GROUP BY month_start
ORDER BY month_start;

-- mart_cohort_retention ----------------------------------------------------------
-- For customers who first signed in the same quarter, what share of their
-- starting ARR (and how many of them) is still here N months later?
CREATE OR REPLACE TABLE mart_cohort_retention AS
WITH starts AS (
    -- Each account's ARR in its very first month.
    SELECT f.account_id, a.cohort_quarter, a.segment,
           f.month_start AS first_month, f.arr AS starting_arr
    FROM fact_arr_monthly f
    JOIN dim_account a ON a.account_id = f.account_id
    WHERE f.arr_change_type = 'new'
),
cohort_size AS (
    SELECT cohort_quarter, segment,
           count(*) AS cohort_accounts, sum(starting_arr) AS cohort_starting_arr,
           -- the newest member's first month limits how far we can look ahead
           date_diff('month', max(first_month), DATE '{last_month}') AS max_observed_month
    FROM starts
    GROUP BY cohort_quarter, segment
),
progress AS (
    SELECT s.cohort_quarter, s.segment,
           date_diff('month', s.first_month, f.month_start) AS months_since_start,
           sum(f.arr)                         AS retained_arr,
           count(*) FILTER (WHERE f.arr > 0)  AS retained_accounts
    FROM starts s
    JOIN fact_arr_monthly f ON f.account_id = s.account_id
    GROUP BY 1, 2, 3
)
SELECT
    p.cohort_quarter,
    p.segment,
    p.months_since_start,
    c.cohort_accounts,
    c.cohort_starting_arr,
    p.retained_accounts,
    p.retained_arr,
    round(p.retained_accounts / c.cohort_accounts, 4)  AS logo_retention,
    round(p.retained_arr / c.cohort_starting_arr, 4)   AS arr_retention
FROM progress p
JOIN cohort_size c USING (cohort_quarter, segment)
WHERE p.months_since_start <= c.max_observed_month
ORDER BY 1, 2, 3;
