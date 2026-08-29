"""
Streamlit UI entrypoint (spec.md section 13.1) -- `make up`/`streamlit run` target.

Initializes both SQLite stores (idempotent `IF NOT EXISTS` DDL, so the app
never crashes against a fresh/empty `data/` directory), then renders the
two vertical sections in order: the Q&A panel on top, the monitoring
dashboard directly below it.
"""

from __future__ import annotations

import streamlit as st

from src.app.dashboard import render_dashboard
from src.app.qa_panel import render_qa_panel
from src.db.knowledge_store import init_db as init_knowledge_db
from src.db.monitoring_store import init_db as init_monitoring_db

st.set_page_config(page_title="MOSFET Selection RAG", layout="wide")


@st.cache_resource
def _init_stores() -> None:
    # Streamlit reruns this whole script on every widget interaction --
    # @st.cache_resource ensures init_db() only actually runs once per
    # server process, not on every rerun.
    init_knowledge_db()
    init_monitoring_db()


_init_stores()

st.title("MOSFET Selection RAG")

render_qa_panel()
render_dashboard()
