"""
Streamlit monitoring dashboard (spec.md section 13.4) -- EXACTLY 5 items:
  1. Summary KPIs (Total Conversations, Average Response Time, Total Cost,
     Average Tokens).
  2. Cost Over Time.
  3. Response Time Over Time.
  4. Judge Relevance Distribution (`source='judge'` only -- never blended
     with `evaluate_llm.py`'s offline `source='eval_judge'` benchmark rows).
  5. User Feedback Comparison ("+1"/"-1" counts, `source='user'` only).

`monitoring_store.py` deliberately exposes no read/aggregation queries
(see its own docstring) -- this module owns all of that SQL. The
aggregation helpers below are factored out from the `st.*` rendering
calls so they can be unit-tested directly against a seeded monitoring
DB without a running Streamlit app. Uncached by design (no
`st.cache_data`) -- this is a local, low-volume SQLite store, and always
showing the latest conversation/feedback matters more than avoiding a
repeated `SELECT` on every rerun.

Handles an empty monitoring store gracefully: every helper below
returns sensible zero/empty-state values instead of raising.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from src.db.monitoring_store import connect

__all__ = ["render_dashboard"]

_JUDGE_LABELS = ("RELEVANT", "PARTLY_RELEVANT", "NON_RELEVANT")


def _fetch_summary_kpis(conn: sqlite3.Connection) -> dict[str, float]:
    """Total conversations, average response time, total cost, average tokens."""
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total_conversations,
            AVG(response_time) AS avg_response_time,
            SUM(cost) AS total_cost,
            AVG(total_tokens) AS avg_tokens
        FROM conversations;
        """
    ).fetchone()
    return {
        "total_conversations": row["total_conversations"] or 0,
        "avg_response_time": row["avg_response_time"] or 0.0,
        "total_cost": row["total_cost"] or 0.0,
        "avg_tokens": row["avg_tokens"] or 0.0,
    }


def _fetch_cost_over_time(conn: sqlite3.Connection) -> pd.DataFrame:
    """Per-conversation cost, indexed by timestamp (oldest first)."""
    rows = conn.execute("SELECT timestamp, cost FROM conversations ORDER BY timestamp ASC;").fetchall()
    if not rows:
        return pd.DataFrame(columns=["cost"])
    return pd.DataFrame([dict(row) for row in rows]).set_index("timestamp")


def _fetch_response_time_over_time(conn: sqlite3.Connection) -> pd.DataFrame:
    """Per-conversation response time, indexed by timestamp (oldest first)."""
    rows = conn.execute(
        "SELECT timestamp, response_time FROM conversations ORDER BY timestamp ASC;"
    ).fetchall()
    if not rows:
        return pd.DataFrame(columns=["response_time"])
    return pd.DataFrame([dict(row) for row in rows]).set_index("timestamp")


def _fetch_judge_relevance_distribution(conn: sqlite3.Connection) -> pd.DataFrame:
    """Counts of RELEVANT/PARTLY_RELEVANT/NON_RELEVANT labels, `source='judge'` only."""
    rows = conn.execute(
        "SELECT label, COUNT(*) AS count FROM feedback WHERE source = 'judge' GROUP BY label;"
    ).fetchall()
    counts = {label: 0 for label in _JUDGE_LABELS}
    for row in rows:
        if row["label"] in counts:
            counts[row["label"]] = row["count"]
    return pd.DataFrame({"count": counts})


def _fetch_user_feedback_comparison(conn: sqlite3.Connection) -> pd.DataFrame:
    """Counts of +1 (up) vs -1 (down) user feedback, `source='user'` only."""
    rows = conn.execute(
        "SELECT score, COUNT(*) AS count FROM feedback WHERE source = 'user' GROUP BY score;"
    ).fetchall()
    counts = {"up": 0, "down": 0}
    for row in rows:
        if row["score"] == 1:
            counts["up"] = row["count"]
        elif row["score"] == -1:
            counts["down"] = row["count"]
    return pd.DataFrame({"count": counts})


def render_dashboard() -> None:
    """Render the monitoring dashboard: exactly the 5 items per spec.md section 13.4."""
    st.header("Monitoring Dashboard")

    with connect() as conn:
        kpis = _fetch_summary_kpis(conn)
        cost_over_time = _fetch_cost_over_time(conn)
        response_time_over_time = _fetch_response_time_over_time(conn)
        judge_distribution = _fetch_judge_relevance_distribution(conn)
        feedback_comparison = _fetch_user_feedback_comparison(conn)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Conversations", kpis["total_conversations"])
    col2.metric("Average Response Time", f"{kpis['avg_response_time']:.2f}s")
    col3.metric("Total Cost", f"${kpis['total_cost']:.4f}")
    col4.metric("Average Tokens", f"{kpis['avg_tokens']:.0f}")

    st.subheader("Cost Over Time")
    st.line_chart(cost_over_time)

    st.subheader("Response Time Over Time")
    st.line_chart(response_time_over_time)

    st.subheader("Judge Relevance Distribution")
    st.bar_chart(judge_distribution)

    st.subheader("User Feedback Comparison")
    st.bar_chart(feedback_comparison)
