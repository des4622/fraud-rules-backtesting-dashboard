"""
streamlit_app.py
----------------
Interactive dashboard for the Fraud Rules Backtesting project.

Run with:
    streamlit run app/streamlit_app.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Fraud Rules Backtesting",
    page_icon="🛡️",
    layout="wide",
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUT_DIR = PROJECT_ROOT / "outputs"

TX_FILE = DATA_DIR / "synthetic_transactions.csv"
ALERTS_FILE = OUT_DIR / "alerts.csv"
PERF_FILE = OUT_DIR / "rule_performance.csv"
TUNE_FILE = OUT_DIR / "threshold_tuning.csv"


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

@st.cache_data
def load_transactions():
    df = pd.read_csv(TX_FILE)
    df["transaction_time"] = pd.to_datetime(df["transaction_time"])
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    return df


@st.cache_data
def load_alerts():
    return pd.read_csv(ALERTS_FILE)


@st.cache_data
def load_rule_performance():
    return pd.read_csv(PERF_FILE)


@st.cache_data
def load_threshold_tuning():
    return pd.read_csv(TUNE_FILE)


@st.cache_data
def join_alerts_with_tx(alerts_df, tx_df):
    return alerts_df.merge(
        tx_df[[
            "transaction_id", "transaction_time", "transaction_date",
            "merchant_category", "channel", "country", "customer_id", "is_fraud",
        ]],
        on="transaction_id",
        how="left",
    )


# ---------------------------------------------------------------------------
# Pre-flight check
# ---------------------------------------------------------------------------

required = {
    "data/synthetic_transactions.csv": TX_FILE,
    "outputs/alerts.csv": ALERTS_FILE,
    "outputs/rule_performance.csv": PERF_FILE,
    "outputs/threshold_tuning.csv": TUNE_FILE,
}
missing = [name for name, p in required.items() if not p.exists()]

if missing:
    st.error(
        "The dashboard needs these files, which are missing:\n\n"
        + "\n".join(f"- `{m}`" for m in missing)
        + "\n\nRun these, then refresh:\n\n"
        "```\npython src/generate_data.py\npython src/rules_engine.py\n"
        "python src/evaluate.py\npython src/threshold_tuning.py\n```"
    )
    st.stop()


tx = load_transactions()
alerts = load_alerts()
perf = load_rule_performance()
tuning = load_threshold_tuning()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

st.sidebar.title("Fraud Rules Dashboard")
st.sidebar.caption("Synthetic data — see README for limitations.")

if st.sidebar.button("Clear data cache"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown(f"**Transactions:** {len(tx):,}")
st.sidebar.markdown(f"**Fraud rate:** {tx['is_fraud'].mean():.2%}")
st.sidebar.markdown(f"**Alert rows:** {len(alerts):,}")
st.sidebar.markdown(f"**Rules:** {perf['rule_id'].nunique()}")


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_overview, tab_perf, tab_tuning, tab_segment, tab_dq = st.tabs([
    "Overview", "Rule Performance", "Threshold Tuning",
    "Segment Heatmap", "Data Quality",
])


# ---------- Tab 1: Overview ----------

with tab_overview:
    st.header("Overview")

    total_tx = len(tx)
    total_alerts = len(alerts)
    unique_flagged = alerts["transaction_id"].nunique()
    fraud_total = int(tx["is_fraud"].sum())

    enriched = join_alerts_with_tx(alerts, tx)
    fraud_caught = int(
        enriched.loc[enriched["is_fraud"] == 1, "transaction_id"].nunique()
    )
    coverage = fraud_caught / fraud_total if fraud_total else 0.0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Transactions", f"{total_tx:,}")
    c2.metric("Alert rows", f"{total_alerts:,}")
    c3.metric("Unique flagged", f"{unique_flagged:,}")
    c4.metric("Fraud caught", f"{fraud_caught:,} / {fraud_total:,}")
    c5.metric("Coverage", f"{coverage:.2%}")

    st.markdown("---")

    daily = (
        enriched.assign(date=enriched["transaction_time"].dt.date)
        .groupby("date")
        .size()
        .reset_index(name="alerts")
    )
    daily["date"] = pd.to_datetime(daily["date"])
    fig = px.line(daily, x="date", y="alerts", title="Daily alert volume (all rules)")
    st.plotly_chart(fig, use_container_width=True)

    by_rule = (
        alerts.groupby(["rule_id", "rule_name"]).size().reset_index(name="alerts")
    ).sort_values("alerts")
    fig = px.bar(
        by_rule, x="alerts", y="rule_id", orientation="h",
        color="rule_id", title="Alert volume by rule",
        hover_data=["rule_name"],
    )
    fig.update_yaxes(title="")
    st.plotly_chart(fig, use_container_width=True)


# ---------- Tab 2: Rule Performance ----------

with tab_perf:
    st.header("Rule Performance")

    severities = sorted(perf["severity"].unique())
    selected = st.multiselect("Filter by severity", severities, default=severities)
    view = perf[perf["severity"].isin(selected)].copy()

    st.dataframe(
        view[[
            "rule_id", "rule_name", "severity",
            "total_alerts", "unique_customers", "fraud_alerts",
            "precision_proxy", "false_positive_proxy",
            "detection_rate_proxy", "alert_rate",
        ]],
        use_container_width=True, hide_index=True,
    )

    bar = view.melt(
        id_vars=["rule_id"],
        value_vars=["total_alerts", "fraud_alerts"],
        var_name="metric", value_name="count",
    )
    fig = px.bar(
        bar, x="rule_id", y="count", color="metric", barmode="group",
        title="Total alerts vs fraud alerts per rule",
    )
    st.plotly_chart(fig, use_container_width=True)

    fig = px.scatter(
        view, x="detection_rate_proxy", y="precision_proxy",
        size="total_alerts", color="rule_id", hover_name="rule_name",
        title="Precision vs detection (bubble size = alert volume)",
        labels={
            "detection_rate_proxy": "Detection rate proxy",
            "precision_proxy": "Precision proxy",
        },
    )
    st.plotly_chart(fig, use_container_width=True)


# ---------- Tab 3: Threshold Tuning ----------

with tab_tuning:
    st.header("Threshold Tuning — High Amount Rule")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=tuning["threshold"], y=tuning["alerts"],
        mode="lines+markers", name="Alerts",
    ))
    fig.add_trace(go.Scatter(
        x=tuning["threshold"], y=tuning["detection_rate_proxy"],
        mode="lines+markers", name="Detection proxy (right axis)",
        yaxis="y2",
    ))
    fig.update_layout(
        title="Threshold vs alert volume and detection",
        xaxis=dict(title="Threshold", type="log"),
        yaxis=dict(title="Alert count"),
        yaxis2=dict(title="Detection proxy", overlaying="y", side="right"),
    )
    st.plotly_chart(fig, use_container_width=True)

    fig2 = px.line(
        tuning, x="threshold", y="precision_proxy", markers=True,
        title="Precision proxy vs threshold",
    )
    fig2.update_xaxes(type="log")
    st.plotly_chart(fig2, use_container_width=True)

    p = tuning["precision_proxy"].values
    r = tuning["detection_rate_proxy"].values
    with np.errstate(invalid="ignore", divide="ignore"):
        f1 = 2 * p * r / (p + r)
    f1 = np.nan_to_num(f1)
    best_idx = int(f1.argmax())

    fig3 = px.line(
        tuning.assign(f1=f1), x="threshold", y="f1", markers=True,
        title="F1 vs threshold",
    )
    fig3.add_vline(
        x=int(tuning.iloc[best_idx]["threshold"]),
        line_dash="dash", line_color="red",
        annotation_text=f"Best: {int(tuning.iloc[best_idx]['threshold']):,}",
    )
    fig3.update_xaxes(type="log")
    st.plotly_chart(fig3, use_container_width=True)

    st.subheader("Sweep table")
    st.dataframe(tuning, use_container_width=True, hide_index=True)


# ---------- Tab 4: Segment Heatmap ----------

with tab_segment:
    st.header("Segment Heatmap")
    enriched = join_alerts_with_tx(alerts, tx)

    dims = ["merchant_category", "channel", "country"]
    row_dim = st.selectbox("Row dimension", dims, index=0)
    col_dim = st.selectbox(
        "Column dimension", [d for d in dims if d != row_dim], index=0
    )

    seg_tx = (
        tx.groupby([row_dim, col_dim]).size().reset_index(name="transactions")
    )
    seg_alerts = (
        enriched.groupby([row_dim, col_dim]).size().reset_index(name="alerts")
    )
    seg = (
        seg_tx.merge(seg_alerts, on=[row_dim, col_dim], how="left")
        .fillna({"alerts": 0})
    )
    seg["alert_rate"] = seg["alerts"] / seg["transactions"]

    pivot = (
        seg.pivot(index=row_dim, columns=col_dim, values="alert_rate").fillna(0)
    )
    fig = px.imshow(
        pivot, text_auto=".1%", aspect="auto", color_continuous_scale="OrRd",
        title=f"Alert rate: {row_dim} × {col_dim}",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(
        seg.sort_values("alert_rate", ascending=False),
        use_container_width=True, hide_index=True,
    )


# ---------- Tab 5: Data Quality ----------

with tab_dq:
    st.header("Data Quality")

    n = len(tx)
    checks = []

    def add_check(name, fail_count, threshold=0):
        status = "PASS" if fail_count <= threshold else "FAIL"
        checks.append({"check": name, "issues": int(fail_count), "status": status})

    for col in ["transaction_id", "customer_id", "amount", "transaction_time", "is_fraud"]:
        add_check(f"Nulls in {col}", tx[col].isna().sum())

    add_check("Duplicate transaction_id", tx["transaction_id"].duplicated().sum())
    add_check("Negative amounts", (tx["amount"] < 0).sum())

    now = pd.Timestamp.now()
    add_check("Future timestamps", (tx["transaction_time"] > now).sum())

    valid_countries = {"HK", "SG", "UK", "US", "AU", "JP", "CA", "MY", "TW", "TH"}
    add_check("Invalid country codes", (~tx["country"].isin(valid_countries)).sum())

    p999 = tx["amount"].quantile(0.999)
    add_check(
        f"Amount > p99.9 ({p999:,.0f})",
        (tx["amount"] > p999).sum(),
        threshold=int(n * 0.002),  # allow up to 0.2% above the 0.1% expected
    )

    st.dataframe(pd.DataFrame(checks), use_container_width=True, hide_index=True)

    null_rate = tx.isna().mean().sort_values(ascending=False)
    null_rate = null_rate[null_rate > 0]
    if len(null_rate):
        fig = px.bar(
            x=null_rate.values, y=null_rate.index, orientation="h",
            title="Null rate by column",
            labels={"x": "Null rate", "y": "Column"},
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.success("No null values found in any column.")

    fig = px.histogram(
        tx, x="amount", color="is_fraud", nbins=80,
        title="Amount distribution by fraud label",
        barmode="overlay", opacity=0.65, log_y=True,
    )
    st.plotly_chart(fig, use_container_width=True)