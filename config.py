"""
config.py: every setting for the project lives here.

Why one file? If your laptop struggles, or you want a bigger dataset, you change
ONE number here instead of hunting through every script.

Any setting below that reads os.environ can be overridden without editing code,
for example (Mac/Linux):   CHURNLENS_ACCOUNTS=1000 uv run run.py generate
                (Windows): $env:CHURNLENS_ACCOUNTS=1000; uv run run.py generate
"""

import os
from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
# PROJECT_ROOT is the folder this file sits in. Building every other path from it
# means the scripts work no matter which folder you run them from.
PROJECT_ROOT = Path(__file__).resolve().parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"  # output of generate/ (pretend "source systems")
EVENTS_DIR = RAW_DIR / "events"  # one Parquet file per month of product events
TRUTH_DIR = RAW_DIR / "_truth"  # hidden answers; the pipeline must NEVER read these
WAREHOUSE_PATH = DATA_DIR / "warehouse.duckdb"  # built in Phase 2

# --------------------------------------------------------------------------
# Randomness
# --------------------------------------------------------------------------
# A fixed seed means every run produces the exact same data. That makes bugs
# reproducible and means your screenshots match what a reviewer generates.
SEED = int(os.environ.get("CHURNLENS_SEED", "42"))

# --------------------------------------------------------------------------
# Size of the fake company
# --------------------------------------------------------------------------
N_ACCOUNTS = int(os.environ.get("CHURNLENS_ACCOUNTS", "3000"))
N_CSMS = 30  # customer success managers who own the accounts

# Customers can sign their FIRST contract any time in this range. Starting in
# 2022 means some customers are already mid-contract when telemetry begins.
FIRST_SIGNUP_START = "2022-01-01"
FIRST_SIGNUP_END = "2025-06-30"

# The window where we have telemetry (usage events and support tickets).
TELEMETRY_START = "2023-01-01"
TELEMETRY_END = "2025-12-31"

# --------------------------------------------------------------------------
# Business shape
# --------------------------------------------------------------------------
# Share of accounts in each segment. Must add up to 1.0.
SEGMENT_MIX = {"SMB": 0.55, "Mid-Market": 0.30, "Enterprise": 0.15}

# Licensed seats on a first contract, as (low, high) per segment.
SEATS_RANGE = {"SMB": (3, 12), "Mid-Market": (12, 40), "Enterprise": (40, 150)}

# Products (plans). Price is list price per seat per month, in US dollars.
PRODUCTS = [
    {"product_id": "P-STARTER", "product_name": "ChurnLens Starter", "tier": "Starter", "list_price_per_seat": 25},
    {"product_id": "P-PRO", "product_name": "ChurnLens Pro", "tier": "Pro", "list_price_per_seat": 45},
    {"product_id": "P-ENT", "product_name": "ChurnLens Enterprise", "tier": "Enterprise", "list_price_per_seat": 80},
]

CONTRACT_MONTHS = 12  # every contract is a 1-year term

# Support SLA: hours allowed until the FIRST response, by ticket priority.
SLA_TARGET_HOURS = {"P1": 1, "P2": 4, "P3": 24}

# --------------------------------------------------------------------------
# Telemetry volume
# --------------------------------------------------------------------------
# Average number of logged "key actions" per active user per month. Raise it for
# more events, lower it for a lighter laptop. About 1.7M events with the defaults.
EVENTS_PER_ACTIVE_USER = 1.3

# Small amounts of deliberately messy data, so Phase 2 cleaning has real work.
DUPLICATE_EVENT_RATE = 0.003  # 0.3% of events are sent twice
TICKET_UPDATE_RATE = 0.02  # 2% of tickets appear twice (an older and a newer version)

# --------------------------------------------------------------------------
# Memory safety
# --------------------------------------------------------------------------
# DuckDB will use at most this much RAM and spill the rest to disk.
DUCKDB_MEMORY_LIMIT = "2GB"
