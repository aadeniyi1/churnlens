# Model card: ChurnLens churn model

A short, honest description of what the model does, how it was tested, and where it falls short.
Numbers are from the default dataset (`seed 42`) and are rewritten to `data/models/metrics.json` on every run.

## What it predicts

The probability that a customer does **not renew** at its next renewal date.
The dashboard multiplies it by ARR to get **ARR at risk**, which is how the Risk List is sorted.

## Who it is for

Customer success leaders and CSMs, to decide which accounts to review first.
It ranks accounts. It does not decide anything on its own.

## Training data

- One row per account per month (`mart_account_month`), Jan 2023 to Dec 2025, synthetic.
- **Only snapshots taken 3 or more months before the renewal date** are used for training, so the model learns
  from signals that arrive early enough to act on.
- Label: 1 if that contract churned at renewal, else 0. Contracts still running are left out.

## Features

Seat utilization (last 3 months) and its 3-month change, utilization in the first 90 days, share of usage
in sticky features, tickets and urgent tickets per 10 seats, SLA breach rate, CSAT, months to renewal,
tenure, ARR (log), seats, segment, and whether the account shrank at its last renewal.

## How it was tested

- **Time-based split:** trained on renewals before 2025, tested on 2025 renewals the model never saw.
- **Headline test:** one snapshot per contract, taken 4 months before renewal (2,072 contracts, 22% churned).

| Approach | ROC AUC | PR AUC | Precision in top 10% | Churned ARR caught in top 10% |
|---|---|---|---|---|
| Logistic regression (baseline) | 0.85 | 0.64 | 75% | 27% |
| **Gradient boosting (in use)** | **0.86** | **0.70** | **80%** | **50%** |
| Rule-based health score | 0.81 | 0.59 | 74% | 42% |

The model is chosen by PR AUC, because finding the minority of churners matters more than ranking everyone.

The rule-based **health score** is only a little less accurate and fully explainable, so the dashboard shows
both. Its tiers separate customers well: in the test set, 9% of "Healthy" accounts churned, 35% of "Watch",
and 73% of "At risk".

**Check against the hidden truth:** with synthetic data we know each account's true risk. The model's risk
ranking has a rank correlation of about 0.5 with it. That is good but not perfect, as expected, because
renewals are partly random and some churn ("surprise churn") leaves no trace in the data.

## What drives it

Seat utilization is by far the strongest signal, followed by the change in utilization, account size,
ticket volume per seat, and CSAT. This matches the Phase 3 analysis.

## Limitations

- **Synthetic data.** The patterns were designed in `generate/`. On real data, expect lower accuracy and
  different drivers.
- **Surprise churn** (acquisitions, budget cuts) can't be predicted from product data.
- **Probabilities for accounts 1–2 months from renewal** are extrapolated, because training only used
  snapshots 3+ months out. Treat those as a late warning.
- **Reasons** on the Risk List come from the rule-based score, not from the model's internals.
  They explain what is wrong with the account, which is what a CSM needs, but not exactly why the
  model gave its number.
