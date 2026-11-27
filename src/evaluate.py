"""
evaluate.py
-----------
Computes per-rule performance metrics by joining ``outputs/alerts.csv``
with the synthetic fraud labels in ``data/synthetic_transactions.csv``.

Outputs
-------
outputs/rule_performance.csv
    One row per rule, with columns:
        rule_id, rule_name, severity,
        total_alerts, unique_customers, fraud_alerts,
        precision_proxy, false_positive_proxy,
        detection_rate_proxy, alert_rate

Usage
-----
    python src/evaluate.py
"""

import os
import pandas as pd

DATA_DIR = "data"
OUT_DIR = "outputs"
TRANSACTIONS_FILE = os.path.join(DATA_DIR, "synthetic_transactions.csv")
ALERTS_FILE = os.path.join(OUT_DIR, "alerts.csv")
PERFORMANCE_FILE = os.path.join(OUT_DIR, "rule_performance.csv")


def load_data():
    tx = pd.read_csv(
        TRANSACTIONS_FILE,
        usecols=["transaction_id", "customer_id", "is_fraud"],
    )
    alerts = pd.read_csv(ALERTS_FILE)
    return tx, alerts


def compute_rule_metrics(tx, alerts):
    total_transactions = len(tx)
    total_fraud = int(tx["is_fraud"].sum())

    # Bring customer_id and is_fraud into the alerts table.
    alerts_enriched = alerts.merge(
        tx[["transaction_id", "customer_id", "is_fraud"]],
        on="transaction_id",
        how="left",
    )

    if alerts_enriched["is_fraud"].isna().any():
        n = int(alerts_enriched["is_fraud"].isna().sum())
        raise RuntimeError(
            f"{n} alert rows could not be matched to a transaction. "
            "Did you regenerate data after creating alerts.csv?"
        )

    rows = []
    for rule_id, grp in alerts_enriched.groupby("rule_id", sort=True):
        total_alerts = len(grp)
        unique_customers = int(grp["customer_id"].nunique())
        fraud_alerts = int(grp["is_fraud"].sum())

        precision = fraud_alerts / total_alerts if total_alerts else 0.0
        false_positive = 1.0 - precision
        detection = fraud_alerts / total_fraud if total_fraud else 0.0
        alert_rate = total_alerts / total_transactions if total_transactions else 0.0

        rows.append({
            "rule_id": rule_id,
            "rule_name": grp["rule_name"].iloc[0],
            "severity": grp["severity"].iloc[0],
            "total_alerts": total_alerts,
            "unique_customers": unique_customers,
            "fraud_alerts": fraud_alerts,
            "precision_proxy": round(precision, 4),
            "false_positive_proxy": round(false_positive, 4),
            "detection_rate_proxy": round(detection, 4),
            "alert_rate": round(alert_rate, 6),
        })

    return pd.DataFrame(rows), total_transactions, total_fraud


def compute_union_coverage(tx, alerts):
    """How many of the fraud transactions are caught by at least one rule?"""
    fraud_ids = set(tx.loc[tx["is_fraud"] == 1, "transaction_id"])
    caught_ids = fraud_ids.intersection(set(alerts["transaction_id"]))
    total_fraud = len(fraud_ids)
    coverage_pct = (len(caught_ids) / total_fraud) if total_fraud else 0.0
    return {
        "total_fraud": total_fraud,
        "fraud_caught_by_any_rule": len(caught_ids),
        "fraud_missed": total_fraud - len(caught_ids),
        "coverage_pct": coverage_pct,
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"Loading {TRANSACTIONS_FILE} ...")
    print(f"Loading {ALERTS_FILE} ...")
    tx, alerts = load_data()
    print(f"  transactions: {len(tx):,}")
    print(f"  alert rows  : {len(alerts):,}")
    print()

    perf, total_tx, total_fraud = compute_rule_metrics(tx, alerts)
    perf.to_csv(PERFORMANCE_FILE, index=False)

    line = "-" * 95
    print("Per-rule performance:")
    print(line)
    print(
        f"{'rule':<6s} {'name':<26s} {'sev':<7s} "
        f"{'alerts':>7s} {'fraud':>6s} {'prec':>7s} {'fp':>7s} {'det':>7s} {'rate':>8s}"
    )
    print(line)
    for _, r in perf.iterrows():
        print(
            f"{r['rule_id']:<6s} {r['rule_name']:<26s} {r['severity']:<7s} "
            f"{r['total_alerts']:>7,d} {r['fraud_alerts']:>6,d} "
            f"{r['precision_proxy']:>7.3f} {r['false_positive_proxy']:>7.3f} "
            f"{r['detection_rate_proxy']:>7.3f} {r['alert_rate']:>7.2%}"
        )
    print(line)
    print()

    coverage = compute_union_coverage(tx, alerts)
    print("Union coverage:")
    print(f"  Total fraud transactions : {coverage['total_fraud']:,}")
    print(f"  Caught by at least 1 rule: {coverage['fraud_caught_by_any_rule']:,}")
    print(f"  Missed by all rules      : {coverage['fraud_missed']:,}")
    print(f"  Coverage                 : {coverage['coverage_pct']:.2%}")
    print()
    print(f"Wrote {PERFORMANCE_FILE}")


if __name__ == "__main__":
    main()