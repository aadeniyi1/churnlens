"""
generate/contracts.py: creates every contract and decides each renewal outcome.

Reads:   data/raw/accounts.parquet, data/raw/_truth/account_risk.parquet
Outputs: data/raw/contracts.parquet
         data/raw/_truth/contract_truth.parquet   (hidden per-contract facts)

How it works, for each account:
    1. Its first contract starts on the account's created_date and lasts 12 months.
    2. At the end of each contract we decide what the customer does:
         churned     - they leave (no next contract)
         expanded    - they renew with MORE seats
         contracted  - they renew with FEWER seats
         renewed     - they renew with the same seats
         open        - the contract is still running when our data ends
    3. Riskier accounts are more likely to churn or contract, and less likely to
       expand. A few healthy accounts churn anyway ("surprise" churn: acquired,
       budget cut). Real life has those, and they keep the model honest.

ARR (annual recurring revenue) = seats x price per seat per month x 12 x discount.
"""

import numpy as np
import pandas as pd

import config

# Which plan each segment usually buys, as {product_id: probability}.
PRODUCT_MIX = {
    "SMB": {"P-STARTER": 0.70, "P-PRO": 0.30, "P-ENT": 0.00},
    "Mid-Market": {"P-STARTER": 0.15, "P-PRO": 0.70, "P-ENT": 0.15},
    "Enterprise": {"P-STARTER": 0.00, "P-PRO": 0.30, "P-ENT": 0.70},
}

# Bigger customers negotiate bigger discounts. (low, high) multiplier on list price.
DISCOUNT_RANGE = {"SMB": (0.95, 1.00), "Mid-Market": (0.85, 1.00), "Enterprise": (0.75, 0.95)}

# Extra churn probability by segment, on top of the risk-driven part.
SEGMENT_CHURN_ADJ = {"SMB": 0.05, "Mid-Market": 0.00, "Enterprise": -0.04}

SURPRISE_CHURN_RATE = 0.025  # 2.5% of renewals are lost for reasons usage can't show
UPGRADE_PATH = {"P-STARTER": "P-PRO", "P-PRO": "P-ENT", "P-ENT": "P-ENT"}


def decide_outcome(rng: np.random.Generator, term_risk: float, segment: str) -> tuple[str, bool]:
    """Decide what happens at the end of one contract. Returns (outcome, is_surprise)."""
    if rng.random() < SURPRISE_CHURN_RATE:
        return "churned", True

    # Churn chance grows with risk. Example for a Mid-Market account:
    #   risk 0.10 -> 7.5% chance,   risk 0.50 -> 29.5%,   risk 0.80 -> 46%
    p_churn = np.clip(0.02 + 0.55 * term_risk + SEGMENT_CHURN_ADJ[segment], 0.0, 0.90)
    if rng.random() < p_churn:
        return "churned", False

    # The customer stays. Do they grow, shrink, or stay flat?
    p_expand = 0.35 * (1 - term_risk)
    p_contract = 0.30 * term_risk
    roll = rng.random()
    if roll < p_expand:
        return "expanded", False
    if roll < p_expand + p_contract:
        return "contracted", False
    return "renewed", False


def main() -> None:
    # Use a different seed offset per script, so each script's random stream is
    # independent but still reproducible.
    rng = np.random.default_rng(config.SEED + 1)

    accounts = pd.read_parquet(config.RAW_DIR / "accounts.parquet")
    risk = pd.read_parquet(config.TRUTH_DIR / "account_risk.parquet")
    accounts = accounts.merge(risk, on="account_id")
    prices = {p["product_id"]: p["list_price_per_seat"] for p in config.PRODUCTS}
    data_end = pd.Timestamp(config.TELEMETRY_END)

    contracts = []  # rows for contracts.parquet
    truth = []  # rows for _truth/contract_truth.parquet
    contract_counter = 0

    # A plain Python loop is fine here: ~3,000 accounts x ~3 contracts each.
    for acc in accounts.itertuples(index=False):
        seg = acc.segment
        low, high = config.SEATS_RANGE[seg]
        seats = int(rng.integers(low, high + 1))
        mix = PRODUCT_MIX[seg]
        product = rng.choice(list(mix.keys()), p=list(mix.values()))
        discount = rng.uniform(*DISCOUNT_RANGE[seg])
        start = pd.Timestamp(acc.created_date)
        number = 1

        while True:
            contract_counter += 1
            end = start + pd.DateOffset(months=config.CONTRACT_MONTHS) - pd.Timedelta(days=1)

            # Risk drifts a little from term to term (new champion, reorg, etc.).
            term_risk = float(np.clip(acc.risk + rng.normal(0, 0.08), 0.01, 0.99))

            if end > data_end:
                outcome, surprise = "open", False
            else:
                outcome, surprise = decide_outcome(rng, term_risk, seg)

            contract_id = f"CON-{contract_counter:06d}"
            contracts.append(
                {
                    "contract_id": contract_id,
                    "account_id": acc.account_id,
                    "product_id": product,
                    "contract_number": number,  # 1 = first contract, 2 = first renewal...
                    "start_date": start.date(),
                    "end_date": end.date(),
                    "seats": seats,
                    "arr": round(seats * prices[product] * 12 * discount, 2),
                    "renewal_outcome": outcome,
                }
            )
            truth.append({"contract_id": contract_id, "term_risk": round(term_risk, 4),
                          "surprise_churn": surprise})

            if outcome in ("churned", "open"):
                break  # no next contract

            # Set up the next contract.
            if outcome == "expanded":
                seats = int(np.ceil(seats * rng.uniform(1.10, 1.50)))
                if rng.random() < 0.20:
                    product = UPGRADE_PATH[product]  # sometimes they also upgrade the plan
            elif outcome == "contracted":
                seats = max(1, int(seats * rng.uniform(0.60, 0.90)))
            start = end + pd.Timedelta(days=1)
            number += 1

    contracts = pd.DataFrame(contracts)
    contracts.to_parquet(config.RAW_DIR / "contracts.parquet", index=False)
    pd.DataFrame(truth).to_parquet(config.TRUTH_DIR / "contract_truth.parquet", index=False)

    counts = contracts["renewal_outcome"].value_counts().to_dict()
    print(f"  contracts: {len(contracts):,}  outcomes: {counts}")


if __name__ == "__main__":
    main()
