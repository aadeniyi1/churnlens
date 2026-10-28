"""
generate/accounts.py: creates customer accounts, CSMs, and products.

Outputs (all in data/raw/):
    accounts.parquet          one row per customer account (the "CRM" view)
    csms.parquet              one row per customer success manager
    products.parquet          one row per plan we sell
    _truth/account_risk.parquet   the hidden risk value for each account

THE KEY IDEA: every account gets a secret number called `risk` between 0 and 1.
A risky account will later use the product less, file more angry tickets, and be
more likely to cancel. The pipeline and the model never see this number. They
have to discover the pattern from the data, which is exactly the real-world job.
We save it in _truth/ only so we can check later how well the model did.
"""

import numpy as np
import pandas as pd
from faker import Faker

import config

REGIONS = ["North America", "EMEA", "APAC", "LATAM"]
REGION_WEIGHTS = [0.50, 0.28, 0.15, 0.07]

INDUSTRIES = [
    "Software", "Financial Services", "Healthcare", "Manufacturing",
    "Retail", "Education", "Media", "Logistics", "Telecom", "Public Sector",
]

# Employee size bands, by segment. A real CRM stores a band, not an exact count.
EMPLOYEE_BANDS = {
    "SMB": ["1-50", "51-200"],
    "Mid-Market": ["201-1000", "1001-5000"],
    "Enterprise": ["5001-20000", "20000+"],
}


def make_csms(rng: np.random.Generator, fake: Faker) -> pd.DataFrame:
    """Create the customer success managers. Each one covers a single region."""
    rows = []
    for i in range(config.N_CSMS):
        rows.append(
            {
                "csm_id": f"CSM-{i + 1:03d}",  # e.g. CSM-001
                "csm_name": fake.name(),
                # Spread CSMs over regions roughly in proportion to customers.
                "region": rng.choice(REGIONS, p=REGION_WEIGHTS),
                "team": rng.choice(["Commercial", "Strategic"], p=[0.7, 0.3]),
            }
        )
    csms = pd.DataFrame(rows)

    # Make sure every region has at least one CSM, otherwise some accounts
    # would have nobody to assign them to.
    for j, region in enumerate(REGIONS):
        if region not in set(csms["region"]):
            csms.loc[j, "region"] = region
    return csms


def unique_company_names(fake: Faker, n: int) -> list[str]:
    """Faker sometimes repeats a name. Keep asking until we have n different ones."""
    names: set[str] = set()
    while len(names) < n:
        names.add(fake.company())
    return sorted(names)  # sorted so the order does not depend on set ordering


def make_accounts(
    rng: np.random.Generator, fake: Faker, csms: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (accounts, truth). `truth` holds the hidden risk for each account."""
    n = config.N_ACCOUNTS

    # 1) Segment for every account, using the mix from config.py.
    segments = rng.choice(
        list(config.SEGMENT_MIX.keys()), size=n, p=list(config.SEGMENT_MIX.values())
    )

    # 2) Hidden risk. A Beta(2, 5) distribution gives mostly low values (most
    #    customers are fine) with a long tail of risky ones. Average is about 0.29.
    risk = rng.beta(2, 5, size=n)
    # Small customers are a bit riskier on average, big ones a bit safer.
    risk = risk + np.select([segments == "SMB", segments == "Enterprise"], [0.06, -0.05], 0.0)
    risk = np.clip(risk, 0.01, 0.99)

    # 3) First signup date: a random day inside the configured window.
    start = pd.Timestamp(config.FIRST_SIGNUP_START)
    end = pd.Timestamp(config.FIRST_SIGNUP_END)
    days = rng.integers(0, (end - start).days + 1, size=n)
    signup = start + pd.to_timedelta(days, unit="D")
    # Contracts start on the first of a month, which keeps monthly math simple.
    signup = signup.to_period("M").to_timestamp()

    regions = rng.choice(REGIONS, size=n, p=REGION_WEIGHTS)

    accounts = pd.DataFrame(
        {
            "account_id": [f"ACC-{i + 1:05d}" for i in range(n)],  # e.g. ACC-00042
            "account_name": unique_company_names(fake, n),
            "parent_account_id": None,
            "industry": rng.choice(INDUSTRIES, size=n),
            "region": regions,
            "segment": segments,
            "employee_band": [rng.choice(EMPLOYEE_BANDS[s]) for s in segments],
            "created_date": signup.date,
        }
    )

    # 4) Assign each account a CSM from its own region.
    csm_by_region = csms.groupby("region")["csm_id"].apply(list).to_dict()
    accounts["csm_id"] = [rng.choice(csm_by_region[r]) for r in accounts["region"]]

    # 5) Account hierarchy. Big companies buy through several subsidiaries.
    #    About 30% of Enterprise accounts become "parents", and some Mid-Market
    #    accounts in the same region become their children.
    enterprise_idx = np.flatnonzero(segments == "Enterprise")
    parents = rng.choice(enterprise_idx, size=int(len(enterprise_idx) * 0.30), replace=False)
    available_children = set(np.flatnonzero(segments == "Mid-Market"))
    for p in parents:
        same_region = [c for c in available_children if regions[c] == regions[p]]
        k = min(len(same_region), int(rng.integers(1, 4)))  # 1 to 3 children
        if k == 0:
            continue
        kids = rng.choice(same_region, size=k, replace=False)
        accounts.loc[kids, "parent_account_id"] = accounts.loc[p, "account_id"]
        # A subsidiary shares its parent's industry and tends to share its fate.
        accounts.loc[kids, "industry"] = accounts.loc[p, "industry"]
        risk[kids] = np.clip(0.5 * risk[kids] + 0.5 * risk[p], 0.01, 0.99)
        available_children -= set(kids)

    truth = pd.DataFrame({"account_id": accounts["account_id"], "risk": risk.round(4)})
    return accounts, truth


def main() -> None:
    rng = np.random.default_rng(config.SEED)
    fake = Faker()
    Faker.seed(config.SEED)

    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    config.TRUTH_DIR.mkdir(parents=True, exist_ok=True)

    csms = make_csms(rng, fake)
    accounts, truth = make_accounts(rng, fake, csms)
    products = pd.DataFrame(config.PRODUCTS)

    csms.to_parquet(config.RAW_DIR / "csms.parquet", index=False)
    accounts.to_parquet(config.RAW_DIR / "accounts.parquet", index=False)
    products.to_parquet(config.RAW_DIR / "products.parquet", index=False)
    truth.to_parquet(config.TRUTH_DIR / "account_risk.parquet", index=False)

    n_children = accounts["parent_account_id"].notna().sum()
    print(f"  accounts: {len(accounts):,} ({n_children} are subsidiaries of a parent)")
    print(f"  csms:     {len(csms)}")
    print(f"  products: {len(products)}")


if __name__ == "__main__":
    main()
