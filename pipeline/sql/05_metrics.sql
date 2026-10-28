-- =============================================================================
-- 05_metrics.sql: Net and Gross Revenue Retention (NRR and GRR).
--
-- Kept in its own file so tests/test_metrics.py can run it on a tiny hand-made
-- dataset where we know the right answer. It only needs two tables:
-- fact_arr_monthly (account_id, month_start, arr) and dim_account (account_id, segment).
--
-- For a given month M, look at every account that was paying 12 months earlier:
--   NRR = their ARR now / their ARR then             (expansion can push it over 100%)
--   GRR = their ARR now, capped at ARR then / ARR then  (ignores expansion, max 100%)
-- New customers signed during the year are NOT included. That's the point:
-- retention measures how well you keep and grow the customers you already had.
-- =============================================================================

CREATE OR REPLACE TABLE metric_retention_12m AS
WITH base AS (
    SELECT
        f0.account_id,
        a.segment,
        CAST(f0.month_start + INTERVAL 12 MONTH AS DATE) AS month_start,
        f0.arr                                           AS start_arr,
        -- No row 12 months later means the account churned earlier, so ARR = 0.
        coalesce(f1.arr, 0)                              AS end_arr
    FROM fact_arr_monthly f0
    JOIN dim_account a ON a.account_id = f0.account_id
    LEFT JOIN fact_arr_monthly f1
      ON f1.account_id  = f0.account_id
     AND f1.month_start = CAST(f0.month_start + INTERVAL 12 MONTH AS DATE)
    WHERE f0.arr > 0
      AND CAST(f0.month_start + INTERVAL 12 MONTH AS DATE)
          <= (SELECT max(month_start) FROM fact_arr_monthly)
)
SELECT
    month_start,
    -- GROUPING SETS below computes each segment AND an overall total in one pass.
    CASE WHEN grouping(segment) = 1 THEN 'All' ELSE segment END AS segment,
    count(*)                                         AS starting_customers,
    count(*) FILTER (WHERE end_arr > 0)              AS retained_customers,
    sum(start_arr)                                   AS starting_arr,
    sum(end_arr)                                     AS ending_arr,
    round(sum(end_arr) / sum(start_arr), 4)                      AS nrr,
    round(sum(least(end_arr, start_arr)) / sum(start_arr), 4)    AS grr
FROM base
GROUP BY GROUPING SETS ((month_start, segment), (month_start))
ORDER BY month_start, segment;
