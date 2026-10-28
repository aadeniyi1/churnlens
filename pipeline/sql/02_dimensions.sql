-- =============================================================================
-- 02_dimensions.sql: the "who, what, when" tables of the star schema.
--
-- In a star schema, FACT tables hold events and numbers (contracts, usage,
-- tickets), and DIMENSION tables describe the things those facts are about
-- (accounts, products, dates). Facts point to dimensions with keys like
-- account_id, so you can slice any number by segment, region, month, and so on.
-- =============================================================================

-- dim_date: one row per calendar day ---------------------------------------------
-- Having a date table lets dashboards group by month or quarter with a simple
-- join instead of repeating date math in every query.
CREATE OR REPLACE TABLE dim_date AS
SELECT
    CAST(d AS DATE)                               AS date,
    year(d)                                       AS year,
    quarter(d)                                    AS quarter,
    month(d)                                      AS month,
    strftime(d, '%Y-%m')                          AS year_month,
    year(d) || '-Q' || quarter(d)                 AS year_quarter,
    CAST(date_trunc('month', d) AS DATE)          AS month_start,
    CAST(d AS DATE) = last_day(CAST(d AS DATE))   AS is_month_end,
    dayname(d)                                    AS day_name,
    isodow(d) >= 6                                AS is_weekend
FROM range(DATE '2022-01-01', DATE '2027-01-01', INTERVAL 1 DAY) AS t(d);

-- dim_account: one row per customer account, with hierarchy ----------------------
-- ultimate_parent_account_id lets you roll a company's subsidiaries up to the
-- parent, which is how enterprise customers are usually reported.
CREATE OR REPLACE TABLE dim_account AS
WITH first_contract AS (
    SELECT account_id, min(start_date) AS first_contract_date
    FROM stg_contracts
    GROUP BY account_id
),
child_counts AS (
    SELECT parent_account_id AS account_id, count(*) AS child_accounts
    FROM stg_accounts
    WHERE parent_account_id IS NOT NULL
    GROUP BY parent_account_id
)
SELECT
    a.account_id,
    a.account_name,
    a.parent_account_id,
    p.account_name                                        AS parent_account_name,
    coalesce(a.parent_account_id, a.account_id)           AS ultimate_parent_account_id,
    coalesce(c.child_accounts, 0)                         AS child_accounts,
    a.industry,
    a.region,
    a.segment,
    a.employee_band,
    a.csm_id,
    f.first_contract_date,
    -- Cohort = the quarter the customer first signed. Used for retention curves.
    year(f.first_contract_date) || '-Q' || quarter(f.first_contract_date) AS cohort_quarter
FROM stg_accounts a
LEFT JOIN stg_accounts p   ON p.account_id = a.parent_account_id
LEFT JOIN child_counts c   ON c.account_id = a.account_id
LEFT JOIN first_contract f ON f.account_id = a.account_id;

-- dim_product and dim_csm: small lookup tables -----------------------------------
CREATE OR REPLACE TABLE dim_product AS
SELECT * FROM stg_products;

CREATE OR REPLACE TABLE dim_csm AS
SELECT * FROM stg_csms;
