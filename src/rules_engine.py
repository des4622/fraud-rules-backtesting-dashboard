"""
rules_engine.py
---------------
Applies the fraud rules defined in ``config/rules.yaml`` to every
transaction in ``data/synthetic_transactions.csv``.

Output
------
outputs/alerts.csv
    One row per (transaction, rule) hit:
    transaction_id, rule_id, rule_name, severity

Rule types supported
--------------------
* simple    : a pandas query string, e.g. "amount > 10000"
* velocity  : N or more transactions for the same customer in a
              trailing time window (e.g. 3 in 24h)

Usage
-----
    python src/rules_engine.py
"""

import os
import yaml
import pandas as pd

DATA_DIR = "data"
OUT_DIR = "outputs"
TRANSACTIONS_FILE = os.path.join(DATA_DIR, "synthetic_transactions.csv")
RULES_FILE = os.path.join("config", "rules.yaml")
ALERTS_FILE = os.path.join(OUT_DIR, "alerts.csv")


# -------------------------------------------------------------------
# Loading
# -------------------------------------------------------------------

def load_rules(path):
    """Load the list of rule dicts from a YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config["rules"]


def load_transactions(path):
    """Load the synthetic transactions and parse the time column."""
    df = pd.read_csv(path)
    df["transaction_time"] = pd.to_datetime(df["transaction_time"])
    return df


# -------------------------------------------------------------------
# Rule evaluation
# -------------------------------------------------------------------

def apply_simple_rule(df, rule):
    """Evaluate a pandas-query style condition and return the alert rows."""
    hits = df.query(rule["condition"])
    return hits[["transaction_id"]].assign(
        rule_id=rule["rule_id"],
        rule_name=rule["name"],
        severity=rule["severity"],
    ).reset_index(drop=True)


def apply_velocity_rule(df, rule):
    """
    Flag each transaction that is part of a cluster of ``min_count`` or
    more transactions for the same customer within ``window_hours``.

    Implementation: sort by (customer, time), then use a trailing rolling
    count over the transaction_time index, grouped by customer.
    """
    window = f"{rule['window_hours']}h"
    min_count = rule["min_count"]

    df_sorted = (
        df[["transaction_id", "customer_id", "transaction_time"]]
        .copy()
        .sort_values(["customer_id", "transaction_time"])
        .reset_index(drop=True)
    )

    counts = (
        df_sorted.set_index("transaction_time")
        .groupby("customer_id")["transaction_id"]
        .rolling(window)
        .count()
        .reset_index(level=0, drop=True)
        .reset_index(drop=True)
    )

    hit_mask = counts >= min_count
    hits = df_sorted.loc[hit_mask.values, ["transaction_id"]].copy()
    return hits.assign(
        rule_id=rule["rule_id"],
        rule_name=rule["name"],
        severity=rule["severity"],
    ).reset_index(drop=True)


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"Loading transactions from {TRANSACTIONS_FILE} ...")
    df = load_transactions(TRANSACTIONS_FILE)
    print(f"  rows: {len(df):,}")

    print(f"Loading rules from {RULES_FILE} ...")
    rules = load_rules(RULES_FILE)
    print(f"  rules: {len(rules)}")
    print()

    all_alerts = []
    for rule in rules:
        rule_type = rule.get("type", "simple")
        if rule_type == "simple":
            alerts = apply_simple_rule(df, rule)
        elif rule_type == "velocity":
            alerts = apply_velocity_rule(df, rule)
        else:
            print(f"  [SKIP] Unknown rule type '{rule_type}' in {rule['rule_id']}")
            continue

        print(f"  {rule['rule_id']}  {rule['name']:30s}  -> {len(alerts):>7,} alerts")
        all_alerts.append(alerts)

    alerts_df = pd.concat(all_alerts, ignore_index=True)
    alerts_df.to_csv(ALERTS_FILE, index=False)

    print()
    print("=" * 60)
    print(f"Total alert rows            : {len(alerts_df):,}")
    print(f"Unique transactions flagged : {alerts_df['transaction_id'].nunique():,}")
    print(f"Wrote {ALERTS_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()