"""
model/train.py: trains the churn model and reports how good it is.

Run it with:   uv run run.py model     (trains, then scores every account)

STEP BY STEP
1. Load training rows from features.py (snapshots 90+ days before renewal).
2. Split by TIME, not at random: train on renewals before 2025, test on 2025
   renewals. That copies real life, where you train on the past and predict
   the future. A random split would let the model peek at the same period it
   is tested on, and its scores would look better than they really are.
3. Train two models:
     - Logistic regression: simple, fast, and every feature gets a readable weight.
       This is the baseline any fancier model has to beat.
     - Gradient boosting (HistGradientBoostingClassifier): learns non-linear
       patterns and feature interactions. Usually more accurate.
4. Evaluate both on the 2025 test set. Keep the one with the better PR AUC,
   because finding the (minority) churners is the job, not ranking everyone.
5. Save the model and its metrics to data/models/.

METRICS, IN PLAIN WORDS
    ROC AUC      pick a random churner and a random renewer. How often does the
                 model rank the churner as riskier? 0.5 = coin flip, 1.0 = perfect.
    PR AUC       how well the model finds churners, which matters because churners
                 are the minority (~22%).
    Precision@10%  of the 10% of accounts flagged riskiest, how many really churned?
    ARR captured@10%  what share of all churned ARR sits in that top 10%?
    Brier score  how close the probabilities are to what happened (lower is better).
"""

import json

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

import config
from model.features import CATEGORICAL_FEATURES, NUMERIC_FEATURES, load_snapshots, training_rows
from model.health_score import health_score

MODEL_DIR = config.DATA_DIR / "models"
MODEL_PATH = MODEL_DIR / "churn_model.joblib"
METRICS_PATH = MODEL_DIR / "metrics.json"
TEST_FROM = pd.Timestamp("2025-01-01")  # contracts renewing from this date on = test set
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def build_models() -> dict[str, Pipeline]:
    # The preprocessor scales numbers to a similar range and turns segment into
    # 0/1 columns (SMB, Mid-Market, Enterprise), which is what the models need.
    preprocess = ColumnTransformer(
        [
            ("num", StandardScaler(), NUMERIC_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ]
    )
    return {
        "logistic_regression": Pipeline(
            [("prep", preprocess), ("clf", LogisticRegression(max_iter=1000, C=0.5))]
        ),
        "gradient_boosting": Pipeline(
            [
                ("prep", preprocess),
                ("clf", HistGradientBoostingClassifier(
                    max_iter=200, learning_rate=0.05, max_leaf_nodes=8, min_samples_leaf=200,
                    l2_regularization=1.0, random_state=config.SEED)),
            ]
        ),
    }


def top_share_metrics(y: np.ndarray, p: np.ndarray, arr: np.ndarray, share: float = 0.10) -> dict:
    """Precision and churned-ARR captured among the `share` riskiest rows."""
    n = max(1, int(len(p) * share))
    top = np.argsort(-p)[:n]
    churned_arr = (arr * y).sum()
    return {
        "precision_at_10pct": float(y[top].mean()),
        "arr_captured_at_10pct": float((arr[top] * y[top]).sum() / churned_arr) if churned_arr else 0.0,
    }


def evaluate(y: np.ndarray, p: np.ndarray, arr: np.ndarray) -> dict:
    return {
        "roc_auc": float(roc_auc_score(y, p)),
        "pr_auc": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        **top_share_metrics(y, p, arr),
    }


def one_per_contract(df: pd.DataFrame, months_to_renewal: int = 4) -> pd.DataFrame:
    """The headline test: ONE snapshot per contract, taken ~4 months before renewal."""
    return df[df["months_to_renewal"] == months_to_renewal]


def main() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    rows = training_rows(load_snapshots())
    renewal_date = pd.to_datetime(rows["month_start"]) + pd.to_timedelta(
        rows["months_to_renewal"] * 30, unit="D")
    train, test = rows[renewal_date < TEST_FROM], rows[renewal_date >= TEST_FROM]
    test_headline = one_per_contract(test)
    print(f"  train rows: {len(train):,} (renewals before {TEST_FROM.date()})")
    print(f"  test rows:  {len(test):,}  |  headline test: {len(test_headline):,} contracts, "
          f"one snapshot each, 4 months before renewal")

    results = {}
    fitted = {}
    for name, pipe in build_models().items():
        pipe.fit(train[FEATURES], train["churned"])
        p = pipe.predict_proba(test_headline[FEATURES])[:, 1]
        results[name] = evaluate(test_headline["churned"].to_numpy(), p, test_headline["arr"].to_numpy())
        fitted[name] = pipe

    # The rule-based health score, judged the same way. Lower health = riskier,
    # so 100 - health acts as its "risk" for these metrics.
    hs = health_score(test_headline)["health_score"].to_numpy()
    results["health_score_rules"] = evaluate(
        test_headline["churned"].to_numpy(), (100 - hs) / 100, test_headline["arr"].to_numpy())

    print("\n  Test results (2025 renewals)")
    print(pd.DataFrame(results).T.round(3).to_string())

    best = max(fitted, key=lambda k: results[k]["pr_auc"])
    model = fitted[best]
    print(f"\n  Best model: {best}")

    # Which features matter? Shuffle one feature at a time and see how much the
    # AUC drops. A big drop means the model relies on that feature.
    imp = permutation_importance(
        model, test_headline[FEATURES], test_headline["churned"],
        scoring="roc_auc", n_repeats=5, random_state=config.SEED)
    importance = (
        pd.Series(imp.importances_mean, index=FEATURES).sort_values(ascending=False).round(4)
    )
    print("\n  Feature importance (drop in ROC AUC when shuffled)")
    print(importance.head(8).to_string())

    # Churn rate by health tier: does the rule-based score separate accounts?
    tiers = health_score(test_headline)["health_tier"]
    by_tier = test_headline.groupby(tiers)["churned"].agg(["count", "mean"]).round(3)
    print("\n  Actual churn rate by health tier (test set)")
    print(by_tier.to_string())

    joblib.dump({"model": model, "name": best, "features": FEATURES}, MODEL_PATH)
    METRICS_PATH.write_text(json.dumps({
        "best_model": best,
        "test_period": f"renewals on or after {TEST_FROM.date()}",
        "train_rows": len(train),
        "test_contracts": len(test_headline),
        "test_churn_rate": float(test_headline["churned"].mean()),
        "results": results,
        "feature_importance": importance.to_dict(),
        "churn_rate_by_health_tier": by_tier["mean"].to_dict(),
    }, indent=2))
    print(f"\n  saved {MODEL_PATH.name} and {METRICS_PATH.name} to {MODEL_DIR}")


if __name__ == "__main__":
    main()
