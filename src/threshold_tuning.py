"""
threshold_tuning.py
-------------------
Sweeps the amount threshold for the 'High Amount' rule (R001) and
reports alert volume, precision proxy, detection proxy and alert rate
at each threshold.

This is the operational trade-off that fraud strategy teams tune:
    threshold too low  -> too many alerts (analyst overload, low precision)
    threshold too high -> miss fraud (low detection, low recall)

Output
------
outputs/threshold_tuning.csv
    One row per threshold, with columns:
        threshold, alerts, fraud_alerts, precision_proxy,
        detection_rate_proxy, alert_rate

Usage
-----
    python src/threshold_tuning.py
"""

import os
import numpy as np
import pandas as pd

DATA_DIR = "data"
OUT_DIR = "outputs"
TRANSACTIONS_FILE = os.path.join(DATA_DIR, "synthetic_transactions.csv")
TUNING_FILE = os.path.join(OUT_DIR, "threshold_tuning.csv")

# Thresholds to sweep, in local currency units.
# Denser in 1k–20k (where the interesting transition happens),
# sparser above 20k.
THRESHOLDS = [
    1_000, 2_000, 3_000, 4_000, 5_000,
    6_000, 7_000, 8_000, 9_000, 10_000,
    12_000, 14_000, 16_000, 18_000, 20_000,
    25_000, 30_000, 40_000, 50_000,
]


def load_data():
    tx = pd.read_csv(
        TRANSACTIONS_FILE,
        usecols=["transaction_id", "amount", "is_fraud"],
    )
    return tx, len(tx), int(tx["is_fraud"].sum())


def sweep(tx, total_tx, total_fraud, thresholds):
    amounts = tx["amount"].values
    is_fraud = tx["is_fraud"].values

    rows = []
    for t in thresholds:
        hit = amounts > t
        alerts = int(hit.sum())
        fraud_alerts = int((hit & (is_fraud == 1)).sum())
        precision = fraud_alerts / alerts if alerts else 0.0
        detection = fraud_alerts / total_fraud if total_fraud else 0.0
        alert_rate = alerts / total_tx if total_tx else 0.0
        rows.append({
            "threshold": t,
            "alerts": alerts,
            "fraud_alerts": fraud_alerts,
            "precision_proxy": round(precision, 4),
            "detection_rate_proxy": round(detection, 4),
            "alert_rate": round(alert_rate, 6),
        })
    return pd.DataFrame(rows)


def find_best_f1(df):
    """Pick the threshold that maximises F1 = 2PR / (P + R)."""
    p = df["precision_proxy"].values
    r = df["detection_rate_proxy"].values
    with np.errstate(invalid="ignore", divide="ignore"):
        f1 = 2 * p * r / (p + r)
    f1 = np.nan_to_num(f1, nan=0.0)
    return int(f1.argmax()), f1


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"Loading {TRANSACTIONS_FILE} ...")
    tx, total_tx, total_fraud = load_data()
    print(f"  transactions: {total_tx:,}")
    print(f"  fraud       : {total_fraud:,}")
    print()

    df = sweep(tx, total_tx, total_fraud, THRESHOLDS)
    df.to_csv(TUNING_FILE, index=False)

    best_idx, f1 = find_best_f1(df)

    line = "-" * 80
    print("Threshold sweep (High Amount rule):")
    print(line)
    print(
        f"{'threshold':>10s} {'alerts':>8s} {'fraud':>7s} "
        f"{'prec':>7s} {'det':>7s} {'alert_rate':>11s} {'F1':>7s}"
    )
    print(line)
 #   for i, r in df.iterrows():
 #       marker = "  <-- best F1" if i == best_idx else ""
 #       print(
 #           f"{r['threshold']:>10,d} {r['alerts']:>8,d} {r['fraud_alerts']:>7,d} "
 #           f"{r['precision_proxy']:>7.3f} {r['detection_rate_proxy']:>7.3f} "
 #           f"{r['alert_rate']:>10.2%} {f1[i]:>7.3f}{marker}"
 #       )
    for i, r in df.iterrows():
        marker = "  <-- best F1" if i == best_idx else ""
        print(
            f"{int(r['threshold']):>10,d} {int(r['alerts']):>8,d} {int(r['fraud_alerts']):>7,d} "
            f"{r['precision_proxy']:>7.3f} {r['detection_rate_proxy']:>7.3f} "
            f"{r['alert_rate']:>10.2%} {f1[i]:>7.3f}{marker}"
        )
    print(line)
    print()

    best = df.iloc[best_idx]
    print(f"Recommended threshold (max F1): {int(best['threshold']):,}")
    print(f"  alerts              : {int(best['alerts']):,}")
    print(f"  precision_proxy     : {best['precision_proxy']:.3f}")
    print(f"  detection_rate_proxy: {best['detection_rate_proxy']:.3f}")
    print()
    print(f"Wrote {TUNING_FILE}")


if __name__ == "__main__":
    main()