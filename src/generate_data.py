
# Deliverable 2 — `src/generate_data.py`

"""
generate_data.py
----------------
Generates synthetic transaction data for the Fraud Rules Backtesting
& Alert Performance Dashboard project.

All transactions, customers, and fraud labels are synthetic and should
not be interpreted as real banking data. The output is designed so that
each fraud rule in ``config/rules.yaml`` has a meaningfully different
performance profile, which makes rule backtesting and threshold tuning
interesting.

Outputs
-------
data/customers.csv
data/synthetic_transactions.csv

Usage
-----
    python src/generate_data.py
"""

import os
import numpy as np
import pandas as pd
from datetime import datetime

# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

SEED = 42

N_CUSTOMERS = 20_000
N_BASE_TRANSACTIONS = 100_000
N_BURST_CUSTOMERS = 2_000         # customers who get a velocity burst
N_FRAUD_BURST_CUSTOMERS = 150     # of those, how many bursts are fraud
FRAUD_RATE_IN_BASE = 0.010        # fraud rate in base (non-burst) population

START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 6, 30)  # 180 days
N_DAYS = (END_DATE - START_DATE).days

COUNTRIES = ["HK", "SG", "UK", "US", "AU", "JP", "CA", "MY", "TW", "TH"]
COUNTRY_WEIGHTS = [0.35, 0.15, 0.10, 0.10, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05]

MERCHANT_CATEGORIES = [
    "Retail", "Dining", "Travel", "Grocery", "Online",
    "Electronics", "Fuel", "Entertainment", "Healthcare", "Education",
]
MERCHANT_WEIGHTS = [0.15, 0.15, 0.08, 0.12, 0.15, 0.07, 0.08, 0.08, 0.07, 0.05]

CHANNELS = ["POS", "Online", "Mobile", "ATM"]
CHANNEL_WEIGHTS = [0.35, 0.25, 0.30, 0.10]

# Hour-of-day weights (index = hour 0..23).
# Most activity during business hours; very little at 2–5am.
HOUR_WEIGHTS = np.array([
    0.02, 0.01, 0.01, 0.01, 0.01, 0.02, 0.03, 0.04,
    0.05, 0.06, 0.06, 0.06, 0.06, 0.06, 0.06, 0.06,
    0.06, 0.05, 0.05, 0.04, 0.04, 0.03, 0.03, 0.02,
])
HOUR_WEIGHTS = HOUR_WEIGHTS / HOUR_WEIGHTS.sum()

# Base amount distribution (lognormal, in local currency units).
BASE_AMOUNT_MEAN = 5.0    # e^5  ≈ 148
BASE_AMOUNT_SIGMA = 1.0

# Fraud amount distribution (boosted high amount).
FRAUD_HIGH_AMOUNT_MEAN = 9.5   # e^9.5 ≈ 13,360
FRAUD_HIGH_AMOUNT_SIGMA = 0.6

# Probability that a NORMAL transaction exhibits each "risky" signal.
P_NORMAL_HIGH_AMOUNT = 0.05
P_NORMAL_GEO_MISMATCH = 0.08
P_NORMAL_NEW_DEVICE = 0.10
P_NORMAL_UNUSUAL_HOUR = 0.08

# Probability that a FRAUD transaction exhibits each risk signal.
P_FRAUD_HIGH_AMOUNT = 0.55
P_FRAUD_GEO_MISMATCH = 0.40
P_FRAUD_NEW_DEVICE = 0.50
P_FRAUD_UNUSUAL_HOUR = 0.30

OUT_DIR = "data"
TRANSACTIONS_FILE = os.path.join(OUT_DIR, "synthetic_transactions.csv")
CUSTOMERS_FILE = os.path.join(OUT_DIR, "customers.csv")


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _make_timestamps(n, rng, start_date, n_days, hour_probs):
    """Return an array of pandas Timestamps within [start_date, start_date + n_days)."""
    days = rng.integers(0, n_days, size=n)
    hours = rng.choice(24, size=n, p=hour_probs)
    minutes = rng.integers(0, 60, size=n)
    seconds = rng.integers(0, 60, size=n)
    return (
        pd.Timestamp(start_date)
        + pd.to_timedelta(days, unit="D")
        + pd.to_timedelta(hours, unit="h")
        + pd.to_timedelta(minutes, unit="m")
        + pd.to_timedelta(seconds, unit="s")
    )


def _pick_alternate_country(home_arr, rng):
    """Return an array of countries that are guaranteed different from home."""
    n = len(home_arr)
    new = rng.choice(COUNTRIES, size=n, p=COUNTRY_WEIGHTS).astype(object)
    same = new == home_arr
    if same.any():
        new[same] = np.where(home_arr[same] != "US", "US", "HK")
    return new


# -------------------------------------------------------------------
# Generation
# -------------------------------------------------------------------

def generate_customers(rng):
    customer_ids = [f"C{str(i).zfill(6)}" for i in range(1, N_CUSTOMERS + 1)]
    home_countries = rng.choice(COUNTRIES, size=N_CUSTOMERS, p=COUNTRY_WEIGHTS)
    home_devices = [f"D{str(i).zfill(8)}" for i in range(1, N_CUSTOMERS + 1)]
    risk_tiers = rng.choice(
        ["LOW", "MEDIUM", "HIGH"], size=N_CUSTOMERS, p=[0.75, 0.20, 0.05]
    )
    return pd.DataFrame(
        {
            "customer_id": customer_ids,
            "home_country": home_countries,
            "home_device_id": home_devices,
            "risk_tier": risk_tiers,
        }
    )


def generate_base_transactions(customers, rng):
    """Generate the base (non-burst) transaction population."""
    n = N_BASE_TRANSACTIONS

    # Skewed customer activity: a few heavy users, many light users.
    activity = rng.dirichlet(np.ones(len(customers)) * 0.5)
    customer_idx = rng.choice(len(customers), size=n, p=activity)
    cust = customers.iloc[customer_idx].reset_index(drop=True)

    timestamps = _make_timestamps(n, rng, START_DATE, N_DAYS, HOUR_WEIGHTS)

    amounts = np.round(
        rng.lognormal(mean=BASE_AMOUNT_MEAN, sigma=BASE_AMOUNT_SIGMA, size=n), 2
    )

    # Country: mostly home, sometimes travel.
    travel_mask = rng.random(n) < P_NORMAL_GEO_MISMATCH
    travel_country = rng.choice(COUNTRIES, size=n, p=COUNTRY_WEIGHTS)
    countries = np.where(travel_mask, travel_country, cust["home_country"].values)

    # Device: mostly home, sometimes new.
    is_new_device = (rng.random(n) < P_NORMAL_NEW_DEVICE).astype(int)
    new_device_ids = np.array(
        [f"DN{str(v).zfill(8)}" for v in rng.integers(1, 10_000_000, size=n)],
        dtype=object,
    )
    device_ids = np.where(
        is_new_device == 1, new_device_ids, cust["home_device_id"].values
    )

    channels = rng.choice(CHANNELS, size=n, p=CHANNEL_WEIGHTS)
    merchants = rng.choice(MERCHANT_CATEGORIES, size=n, p=MERCHANT_WEIGHTS)

    df = pd.DataFrame(
        {
            "transaction_id": [f"T{str(i).zfill(8)}" for i in range(1, n + 1)],
            "customer_id": cust["customer_id"].values,
            "transaction_time": timestamps,
            "amount": amounts,
            "currency": [f"CUR_{c}" for c in countries],
            "merchant_category": merchants,
            "country": countries,
            "home_country": cust["home_country"].values,
            "device_id": device_ids,
            "is_new_device": is_new_device,
            "channel": channels,
            "is_burst": 0,
            "is_fraud": 0,
        }
    )
    return df


def label_base_fraud(df, rng):
    """Randomly mark a small fraction of base transactions as fraud."""
    n_base_fraud = int(round(len(df) * FRAUD_RATE_IN_BASE))
    fraud_idx = rng.choice(df.index, size=n_base_fraud, replace=False)
    df.loc[fraud_idx, "is_fraud"] = 1
    return df


def enhance_fraud_signals(df, rng):
    """
    For rows with is_fraud == 1, probabilistically set risky features.

    This creates the correlation between fraud label and rule triggers
    that backtesting is meant to detect. It is not applied to burst
    transactions (they are already risk-shaped by construction).
    """
    fraud_mask = (df["is_fraud"] == 1) & (df["is_burst"] == 0)
    if not fraud_mask.any():
        return df

    fraud_idx = df.index[fraud_mask]
    n_fraud = len(fraud_idx)

    # --- High amount ---
    boost_amount = rng.random(n_fraud) < P_FRAUD_HIGH_AMOUNT
    high_amounts = np.round(
        rng.lognormal(
            mean=FRAUD_HIGH_AMOUNT_MEAN, sigma=FRAUD_HIGH_AMOUNT_SIGMA, size=n_fraud
        ),
        2,
    )
    current_amounts = df.loc[fraud_idx, "amount"].values
    df.loc[fraud_idx, "amount"] = np.where(
        boost_amount, high_amounts, current_amounts
    )

    # --- Geo mismatch ---
    flip_country = rng.random(n_fraud) < P_FRAUD_GEO_MISMATCH
    home = df.loc[fraud_idx, "home_country"].values
    new_countries = _pick_alternate_country(home, rng)
    current_countries = df.loc[fraud_idx, "country"].values
    df.loc[fraud_idx, "country"] = np.where(
        flip_country, new_countries, current_countries
    )
    # Keep currency consistent with country
    df.loc[fraud_idx, "currency"] = np.where(
        flip_country,
        [f"CUR_{c}" for c in df.loc[fraud_idx, "country"].values],
        df.loc[fraud_idx, "currency"].values,
    )

    # --- New device ---
    flip_device = rng.random(n_fraud) < P_FRAUD_NEW_DEVICE
    new_device_ids = np.array(
        [f"DN{str(v).zfill(8)}" for v in rng.integers(1, 10_000_000, size=n_fraud)],
        dtype=object,
    )
    df.loc[fraud_idx, "is_new_device"] = np.where(flip_device, 1, 0)
    df.loc[fraud_idx, "device_id"] = np.where(
        flip_device,
        new_device_ids,
        df.loc[fraud_idx, "device_id"].values,
    )

    # --- Unusual hour (1–5am) ---
    flip_hour = rng.random(n_fraud) < P_FRAUD_UNUSUAL_HOUR
    ts = df.loc[fraud_idx, "transaction_time"]
    new_hours = rng.integers(1, 6, size=n_fraud)
    new_minutes = rng.integers(0, 60, size=n_fraud)
    new_seconds = rng.integers(0, 60, size=n_fraud)
    new_ts = (
        ts.dt.normalize()
        + pd.Series(pd.to_timedelta(new_hours, unit="h"), index=fraud_idx)
        + pd.Series(pd.to_timedelta(new_minutes, unit="m"), index=fraud_idx)
        + pd.Series(pd.to_timedelta(new_seconds, unit="s"), index=fraud_idx)
    )
    flip_hour_mask = pd.Series(flip_hour, index=fraud_idx)
    df.loc[fraud_idx, "transaction_time"] = ts.where(~flip_hour_mask, new_ts)

    return df


def add_velocity_bursts(df, customers, rng):
    """
    Add explicit velocity bursts: some customers get 3–5 transactions
    within a short window. A subset of these bursts are flagged as fraud.

    This is needed because the base population is too sparse over 180
    days to naturally trigger a "3 transactions in 24 hours" rule.
    """
    burst_customers = customers.sample(
        n=N_BURST_CUSTOMERS, random_state=SEED
    ).reset_index(drop=True)

    fraud_burst_ids = set(
        burst_customers.sample(
            n=N_FRAUD_BURST_CUSTOMERS, random_state=SEED + 1
        )["customer_id"].tolist()
    )

    rows = []
    next_id = int(df["transaction_id"].str[1:].astype(int).max()) + 1

    for _, cust in burst_customers.iterrows():
        day = int(rng.integers(0, N_DAYS))
        start_hour = int(rng.integers(8, 22))
        burst_start = (
            pd.Timestamp(START_DATE)
            + pd.to_timedelta(day, unit="D")
            + pd.to_timedelta(start_hour, unit="h")
        )
        n_burst = int(rng.integers(3, 6))  # 3–5 transactions
        is_fraud_burst = cust["customer_id"] in fraud_burst_ids

        for _ in range(n_burst):
            t = burst_start + pd.to_timedelta(int(rng.integers(0, 360)), unit="m")

            if is_fraud_burst:
                amount = float(
                    np.round(
                        rng.lognormal(
                            mean=FRAUD_HIGH_AMOUNT_MEAN,
                            sigma=FRAUD_HIGH_AMOUNT_SIGMA,
                        ),
                        2,
                    )
                )
                country = (
                    rng.choice(COUNTRIES, p=COUNTRY_WEIGHTS)
                    if rng.random() < P_FRAUD_GEO_MISMATCH
                    else cust["home_country"]
                )
                if country == cust["home_country"]:
                    country = "SG" if cust["home_country"] != "SG" else "HK"
                device_id = (
                    f"DN{str(int(rng.integers(1, 10_000_000))).zfill(8)}"
                    if rng.random() < P_FRAUD_NEW_DEVICE
                    else cust["home_device_id"]
                )
                is_new_device = int(device_id != cust["home_device_id"])
                is_fraud = 1
            else:
                amount = float(
                    np.round(
                        rng.lognormal(
                            mean=BASE_AMOUNT_MEAN, sigma=BASE_AMOUNT_SIGMA
                        ),
                        2,
                    )
                )
                country = cust["home_country"]
                device_id = cust["home_device_id"]
                is_new_device = 0
                is_fraud = 0

            rows.append(
                {
                    "transaction_id": f"T{str(next_id).zfill(8)}",
                    "customer_id": cust["customer_id"],
                    "transaction_time": t,
                    "amount": amount,
                    "currency": f"CUR_{country}",
                    "merchant_category": rng.choice(
                        MERCHANT_CATEGORIES, p=MERCHANT_WEIGHTS
                    ),
                    "channel": rng.choice(CHANNELS, p=CHANNEL_WEIGHTS),
                    "country": country,
                    "home_country": cust["home_country"],
                    "device_id": device_id,
                    "is_new_device": is_new_device,
                    "is_burst": 1,
                    "is_fraud": is_fraud,
                }
            )
            next_id += 1

    burst_df = pd.DataFrame(rows)
    return pd.concat([df, burst_df], ignore_index=True)


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rng = np.random.default_rng(SEED)

    print("[1/5] Generating customers ...")
    customers = generate_customers(rng)

    print("[2/5] Generating base transactions ...")
    df = generate_base_transactions(customers, rng)

    print("[3/5] Labelling fraud in base population ...")
    df = label_base_fraud(df, rng)

    print("[4/5] Enhancing fraud signals + adding velocity bursts ...")
    df = enhance_fraud_signals(df, rng)
    df = add_velocity_bursts(df, customers, rng)

    print("[5/5] Finalising and exporting ...")
    df = df.sort_values("transaction_time").reset_index(drop=True)
    df["transaction_time"] = pd.to_datetime(df["transaction_time"]).dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    df["transaction_date"] = pd.to_datetime(df["transaction_time"]).dt.date
    df["transaction_hour"] = pd.to_datetime(df["transaction_time"]).dt.hour

    cols = [
        "transaction_id",
        "customer_id",
        "transaction_time",
        "transaction_date",
        "transaction_hour",
        "amount",
        "currency",
        "merchant_category",
        "channel",
        "country",
        "home_country",
        "device_id",
        "is_new_device",
        "is_burst",
        "is_fraud",
    ]
    df = df[cols]

    df.to_csv(TRANSACTIONS_FILE, index=False)
    customers.to_csv(CUSTOMERS_FILE, index=False)

    n_total = len(df)
    n_fraud = int(df["is_fraud"].sum())
    n_burst = int(df["is_burst"].sum())
    n_fraud_in_burst = int(df.loc[df["is_burst"] == 1, "is_fraud"].sum())
    n_fraud_in_base = int(df.loc[df["is_burst"] == 0, "is_fraud"].sum())

    print()
    print("=" * 60)
    print(f"Total transactions : {n_total:,}")
    print(f"Fraud transactions : {n_fraud:,} ({n_fraud / n_total:.2%})")
    print(f"Burst transactions : {n_burst:,}")
    print(f"  Fraud in bursts  : {n_fraud_in_burst:,}")
    print(f"  Fraud in base    : {n_fraud_in_base:,}")
    print(f"Unique customers   : {df['customer_id'].nunique():,}")
    print()
    print(f"Wrote {TRANSACTIONS_FILE}")
    print(f"Wrote {CUSTOMERS_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()