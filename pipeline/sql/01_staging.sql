-- =============================================================================
-- 01_staging.sql: clean copies of the raw source files.
--
-- "Staging" is the first layer of a warehouse. Each stg_ table is one source
-- file, read as-is, with only light fixes: correct data types, trimmed text,
-- duplicates removed, and a few helper columns calculated. No business logic yet.
--
-- {raw} is replaced by build.py with the path to data/raw before this runs.
-- =============================================================================

-- Accounts from the CRM ---------------------------------------------------------
CREATE OR REPLACE TABLE stg_accounts AS
SELECT
    account_id,
    trim(account_name)           AS account_name,
    parent_account_id,
    industry,
    region,
    segment,
    employee_band,
    CAST(created_date AS DATE)   AS created_date,
    csm_id
FROM read_parquet('{raw}/accounts.parquet');

CREATE OR REPLACE TABLE stg_csms AS
SELECT csm_id, csm_name, region, team
FROM read_parquet('{raw}/csms.parquet');

CREATE OR REPLACE TABLE stg_products AS
SELECT product_id, product_name, tier, CAST(list_price_per_seat AS DOUBLE) AS list_price_per_seat
FROM read_parquet('{raw}/products.parquet');

-- Contracts from billing ---------------------------------------------------------
CREATE OR REPLACE TABLE stg_contracts AS
SELECT
    contract_id,
    account_id,
    product_id,
    contract_number,
    CAST(start_date AS DATE)   AS start_date,
    CAST(end_date AS DATE)     AS end_date,
    seats,
    CAST(arr AS DOUBLE)        AS arr,
    renewal_outcome
FROM read_parquet('{raw}/contracts.parquet');

-- Product events -----------------------------------------------------------------
-- The '*' reads all 36 monthly files as if they were one table.
-- Some events were delivered twice. A duplicate has the SAME event_id, so we keep
-- exactly one row per event_id. QUALIFY filters on a window function, like a
-- WHERE clause that runs after row_number() is calculated.
CREATE OR REPLACE TABLE stg_events AS
SELECT
    event_id,
    account_id,
    user_id,
    product_id,
    event_type,
    event_ts,
    CAST(event_ts AS DATE)                 AS event_date,
    CAST(date_trunc('month', event_ts) AS DATE) AS event_month
FROM read_parquet('{raw}/events/*.parquet')
QUALIFY row_number() OVER (PARTITION BY event_id ORDER BY event_ts) = 1;

-- Support tickets ----------------------------------------------------------------
-- Some tickets appear twice: an old "open" copy and the newer "resolved" one.
-- Keep the most recently updated version of each ticket.
-- Then calculate the SLA fields the help desk export didn't give us.
CREATE OR REPLACE TABLE stg_tickets AS
WITH latest AS (
    SELECT *
    FROM read_parquet('{raw}/tickets.parquet')
    QUALIFY row_number() OVER (PARTITION BY ticket_id ORDER BY updated_at DESC) = 1
)
SELECT
    ticket_id,
    account_id,
    priority,
    category,
    status,
    created_at,
    first_response_at,
    resolved_at,
    CAST(created_at AS DATE)                      AS created_date,
    CAST(date_trunc('month', created_at) AS DATE) AS created_month,
    -- SLA targets must match SLA_TARGET_HOURS in config.py
    CASE priority WHEN 'P1' THEN 1 WHEN 'P2' THEN 4 ELSE 24 END AS sla_target_hours,
    date_diff('second', created_at, first_response_at) / 3600.0 AS first_response_hours,
    date_diff('second', created_at, resolved_at) / 3600.0       AS resolution_hours,
    -- NULL (unknown) if nobody has responded yet when our data ends
    first_response_hours > sla_target_hours                      AS sla_breached,
    CAST(csat AS INTEGER)                                        AS csat
FROM latest;
