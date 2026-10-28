"""
model/: account health score and churn prediction.

    features.py      builds one row of signals per account per month from the warehouse
    health_score.py  a rule-based 0-100 score with plain-English reasons (explainable)
    train.py         trains and evaluates the machine-learning churn model
    score.py         scores every account and writes fact_account_health to the warehouse
"""
