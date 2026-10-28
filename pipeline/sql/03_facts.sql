-- =============================================================================
-- 03_facts.sql: the measurable events of the business.
--
-- Each fact table has a GRAIN: the one thing a single row represents. Always know
-- the grain before you sum anything, or you will double count.
--   fact_contract      one row per contract
--   fact_arr_monthly   one row per account per month (ARR at month end)
--   fact_usage_daily   one row per account per product per day
--   fact_ticket        one row per support ticket
-- =============================================================================

-- fact_contract ------------------------------------------------------------------
CREATE OR REPLACE TABLE fact_contract AS
SELECT
    c.*,
    c.contract_number > 1                             AS is_renewal,
    lag(c.arr) OVER (PARTITION BY c.account_id ORDER BY c.contract_number) AS prior_arr,
    c.arr - lag(c.arr) OVER (PARTITION BY c.account_id ORDER BY c.contract_number) AS arr_change
FROM stg_contracts c;

-- fact_arr_monthly ---------------------------------------------------------------
-- ARR for every account at the end of every month it was a customer, PLUS the
-- month right after it churned (with ARR = 0). That zero row is what lets us
-- count churn: ARR went from something to nothing.
CREATE OR REPLACE TABLE fact_arr_monthly AS
WITH months AS (
    SELECT CAST(m AS DATE) AS month_start, last_day(CAST(m AS DATE)) AS month_end
    FROM range(DATE '{first_month}', DATE '{last_month}' + INTERVAL 1 DAY, INTERVAL 1 MONTH) AS t(m)
),
spans AS (
    SELECT account_id, min(start_date) AS first_start, max(end_date) AS last_end
    FROM stg_contracts
    GROUP BY account_id
),
-- Every month from the account's first contract until one month after its last.
grid AS (
    SELECT s.account_id, m.month_start, m.month_end
    FROM spans s
    JOIN months m
      ON m.month_start >= date_trunc('month', s.first_start)
     AND m.month_start <= s.last_end + INTERVAL 1 MONTH
),
-- A contract counts toward a month if it is active on the last day of that month.
arr AS (
    SELECT
        g.account_id,
        g.month_start,
        coalesce(sum(c.arr), 0)    AS arr,
        coalesce(sum(c.seats), 0)  AS licensed_seats,
        any_value(c.contract_id)   AS contract_id,
        any_value(c.product_id)    AS product_id
    FROM grid g
    LEFT JOIN stg_contracts c
      ON c.account_id = g.account_id
     AND c.start_date <= g.month_end
     AND c.end_date   >= g.month_end
    GROUP BY g.account_id, g.month_start
),
with_prev AS (
    SELECT *, lag(arr, 1, 0) OVER (PARTITION BY account_id ORDER BY month_start) AS prev_arr
    FROM arr
)
SELECT
    account_id,
    month_start,
    contract_id,
    product_id,
    licensed_seats,
    arr,
    prev_arr,
    arr - prev_arr AS arr_change,
    CASE
        WHEN prev_arr = 0 AND arr > 0 THEN 'new'
        WHEN prev_arr > 0 AND arr = 0 THEN 'churn'
        WHEN arr > prev_arr          THEN 'expansion'
        WHEN arr < prev_arr          THEN 'contraction'
        ELSE 'flat'
    END AS arr_change_type
FROM with_prev;

-- fact_usage_daily ---------------------------------------------------------------
-- Aggregate first (1.7M events -> far fewer rows), THEN join to contracts to get
-- licensed seats. Joining before aggregating would make DuckDB do far more work.
CREATE OR REPLACE TABLE fact_usage_daily AS
WITH daily AS (
    SELECT
        account_id,
        product_id,
        event_date                                    AS date,
        count(*)                                      AS events,
        count(DISTINCT user_id)                       AS active_users,
        count(*) FILTER (WHERE event_type IN ('dashboard_created', 'integration_sync'))
                                                      AS key_feature_events
    FROM stg_events
    GROUP BY account_id, product_id, event_date
)
SELECT d.*, c.seats AS licensed_seats
FROM daily d
LEFT JOIN stg_contracts c
  ON c.account_id = d.account_id
 AND d.date BETWEEN c.start_date AND c.end_date;

-- fact_ticket --------------------------------------------------------------------
CREATE OR REPLACE TABLE fact_ticket AS
SELECT * FROM stg_tickets;
