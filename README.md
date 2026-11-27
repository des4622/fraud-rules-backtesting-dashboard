# Fraud Rules Backtesting & Alert Performance Dashboard

A Python PoC that generates synthetic transaction data, applies a set of
config-driven fraud rules, and produces a Streamlit dashboard to monitor
rule performance, data quality, alert volume, and threshold tuning.

This project is designed as a **portfolio piece** for
*Data Analytics / Fraud Risk / System Migration* roles. It mirrors the
type of work done during a fraud detection system migration: **loading
and preparing data, designing and running tests, automating rule
execution, and reporting on strategy performance.**

> **Disclaimer**
> All transactions, customers, and fraud labels are **100% synthetic**.
> No real bank, customer, or transaction data is used. Any resemblance
> to actual fraud patterns is coincidental and intended only for
> demonstration.

---

## 1. Business Problem

Fraud detection systems rely on **rules and strategies** (velocity,
geo mismatch, new device, amount thresholds, unusual hours). When such
a system is migrated, the bank needs to answer:

1. Do the existing rules still fire on the new data pipeline?
2. What is the **alert volume** and how does it compare to the old system?
3. Are the rules **catching fraud** or just generating noise?
4. What happens to alert volume and detection if we **tune thresholds**?
5. How do we **monitor** all of this once the system is live?

This project answers those questions with a reproducible pipeline and a
single dashboard view.

---

## 2. What the Project Does

| Step | Description |
|------|-------------|
| Data generation | Synthetic transactions (~110k) with realistic distributions and injected fraud patterns |
| Rule engine | 5 configurable rules loaded from YAML |
| Backtesting | Rules applied to every transaction; alerts recorded |
| Evaluation | Alert volume, hit rate, detection / false-positive / precision **proxies** per rule |
| Threshold tuning | High-amount threshold swept from 1k to 50k |
| Data quality | Nulls, duplicates, negative amounts, future timestamps, outliers |
| Dashboard | Streamlit app with 5 tabs: Overview, Rule Performance, Threshold Tuning, Segment Heatmap, Data Quality |

---

## 3. Repository Structure

```
fraud-rules-backtesting-dashboard/
├── README.md
├── requirements.txt
├── .gitignore
├── config/
│   └── rules.yaml
├── data/
│   ├── customers.csv
│   ├── synthetic_transactions.csv
│   └── data_dictionary.md
├── src/
│   ├── generate_data.py
│   ├── rules_engine.py
│   ├── evaluate.py
│   ├── threshold_tuning.py
│   └── data_quality.py
├── app/
│   └── streamlit_app.py
├── outputs/
│   ├── alerts.csv
│   ├── rule_performance.csv
│   ├── threshold_tuning.csv
│   └── dq_summary.csv
└── tests/
    └── test_rules_engine.py
```

---

## 4. Data Dictionary (`data/synthetic_transactions.csv`)

| Column | Type | Description |
|--------|------|-------------|
| `transaction_id` | string | Unique transaction ID (`T########`) |
| `customer_id` | string | Customer ID (`C######`) |
| `transaction_time` | datetime | Timestamp (`YYYY-MM-DD HH:MM:SS`) |
| `transaction_date` | date | Date part |
| `transaction_hour` | int | Hour 0–23 |
| `amount` | float | Transaction amount (local currency) |
| `currency` | string | `CUR_<COUNTRY>` |
| `merchant_category` | string | e.g. Retail, Dining, Online |
| `channel` | string | POS / Online / Mobile / ATM |
| `country` | string | Transaction country |
| `home_country` | string | Customer's home country |
| `device_id` | string | Device used (`D########` home / `DN########` new) |
| `is_new_device` | int | 1 if device ≠ customer's home device |
| `is_burst` | int | 1 if part of an injected velocity burst |
| `is_fraud` | int | **Synthetic** label (1 = fraud). Used only for backtesting |

`data/customers.csv` contains one row per customer:
`customer_id`, `home_country`, `home_device_id`, `risk_tier`.

**Target distributions**

- Total transactions: ~110,000
- Fraud rate: ~1.5% (~1,600 rows)
- ~40% of fraud comes from velocity bursts
- ~60% of fraud comes from base population

---

## 5. Fraud Rules (`config/rules.yaml`)

| ID | Rule | Logic | Severity |
|----|------|-------|----------|
| R001 | High Amount | `amount > 10000` | HIGH |
| R002 | Geo Mismatch | `country != home_country` | MEDIUM |
| R003 | New Device + High Amount | `is_new_device == 1 and amount > 5000` | HIGH |
| R004 | Unusual Hour | `transaction_hour between 1 and 5` | LOW |
| R005 | Velocity 3 in 24h | ≥3 transactions per customer in rolling 24h | MEDIUM |

All thresholds are configurable. R001 is the target of the threshold
tuning module.

---

## 6. Methodology

### Backtesting
Every transaction is evaluated against every rule. If a transaction
triggers a rule, one row is added to `alerts.csv` with
`transaction_id, rule_id, rule_name, severity`.

### Proxy metrics
Because the `is_fraud` label is synthetic, evaluation uses **proxy**
metrics. In a real bank, confirmed fraud, alert triage outcomes, and
case management decisions would be used instead.

| Metric | Definition |
|--------|------------|
| `total_alerts` | Transactions flagged by this rule |
| `unique_customers` | Distinct customers flagged |
| `fraud_alerts` | Flagged transactions with `is_fraud = 1` |
| `detection_rate_proxy` | `fraud_alerts / total fraud transactions` |
| `false_positive_proxy` | `(total_alerts − fraud_alerts) / total_alerts` |
| `precision_proxy` | `fraud_alerts / total_alerts` |
| `alert_rate` | `total_alerts / total transactions` |

### Threshold tuning
For R001, `amount` is swept from 1,000 to 50,000. At each threshold the
system reports alert volume, detection proxy, false-positive proxy, and
precision proxy. This exposes the classic **alert volume vs detection
trade-off** and is directly applicable to fraud strategy tuning.

### Data quality
`data_quality.py` checks:

- Null rate per column
- Duplicate `transaction_id`
- Negative amounts
- Future timestamps
- Invalid country codes
- Amount above 99.9th percentile

---

## 7. How to Run

### Setup

```bash
# 1. Clone and enter the project
git clone <your-repo-url>
cd fraud-rules-backtesting-dashboard

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt
```

`requirements.txt`:

```
pandas>=2.0
numpy>=1.24
pyyaml>=6.0
plotly>=5.18
streamlit>=1.30
openpyxl>=3.1
pytest>=7.4
```

### Run the pipeline

```bash
# Step 1 – generate synthetic data (writes data/)
python src/generate_data.py

# Step 2 – apply fraud rules (writes outputs/alerts.csv)
python src/rules_engine.py

# Step 3 – compute rule performance (writes outputs/rule_performance.csv)
python src/evaluate.py

# Step 4 – threshold tuning (writes outputs/threshold_tuning.csv)
python src/threshold_tuning.py

# Step 5 – data quality checks (writes outputs/dq_summary.csv)
python src/data_quality.py

# Step 6 – launch the dashboard
streamlit run app/streamlit_app.py
```

### Run tests

```bash
pytest -q
```

---

## 8. Expected Outputs

After running the pipeline:

```
data/
  customers.csv                     ~20,000 rows
  synthetic_transactions.csv        ~110,000 rows (~1.5% fraud)

outputs/
  alerts.csv                        one row per (transaction, rule) hit
  rule_performance.csv              one row per rule with proxy metrics
  threshold_tuning.csv              R001 sweep across 20+ thresholds
  dq_summary.csv                    data quality checks + pass/fail
```

The Streamlit dashboard reads from `outputs/` and `data/`.

---

## 9. Key Findings (to fill in after running)

Use this section in the README and in interviews. Suggested framing:

- **R003 (New Device + High Amount)** produced the highest
  `precision_proxy` because the combination is rare in normal traffic
  and common in fraud.
- **R001 (High Amount)** produced the highest alert volume; raising the
  threshold from 10k to 25k reduced alert volume by roughly X% while
  detection proxy fell by only Y% — a favourable trade-off.
- **R002 (Geo Mismatch)** had a high alert volume but low precision,
  suggesting geo alone is noisy and should be combined with velocity
  or device signals.
- **R004 (Unusual Hour)** had a very low precision proxy; it should be
  treated as a *weighting* signal, not a standalone rule.
- **R005 (Velocity)** caught a distinct fraud segment that other rules
  missed (fraud bursts), showing the value of behavioural rules.

> Replace **X%** and **Y%** with numbers from your
> `rule_performance.csv` and `threshold_tuning.csv` after running.

---

## 10. Limitations

- **Synthetic labels** — `is_fraud` is generated, not confirmed.
  All detection / false-positive metrics are proxies.
- **PoC rule parser** — the rules engine uses a simple condition
  evaluator. Production would use a proper rules DSL or vendor engine.
- **No alert triage** — the project scores rules, not individual alerts.
- **No model score** — rules only; no ML model is combined.
- **Single-market data** — no real regional or regulatory variation.

---

## 11. Future Enhancements

- Combine rule alerts into a **risk score** and rank alerts.
- Add **alert prioritisation** by severity and customer segment.
- Build a **model + rules** hybrid scorer (e.g. XGBoost + rules).
- Add **case management** outcomes back into the evaluation.
- Add **alert-to-fraud funnel** visualisation (alert → triage → case).
- Persist outputs to a database instead of CSV for larger datasets.
- Add CI (GitHub Actions) running `pytest` and linting.

---

## 12. Links

- Author: Desmond Lai
- Related projects:
  - [IFRS 9 ECL Modeling Engine](https://github.com/des4622/IFRS_ECL)
  - [GI Pricing & AI Governance PoC](https://github.com/des4622/gi-pricing-ai-governance-poc)

---

## 13. License

For portfolio / educational use only. Synthetic data only.