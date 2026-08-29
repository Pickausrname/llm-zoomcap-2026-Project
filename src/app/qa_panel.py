"""
Streamlit Q&A panel (spec.md section 13.2/13.3).

Renders the query input, submit button, spinner, generated answer +
execution metrics, and the "+1"/"-1" feedback buttons. Immediately
after a successful `generate_answer()` call, the answer + metrics are
rendered via `st.write` FIRST -- Streamlit streams UI elements as the
script executes, so the user sees their answer the instant that line
runs. ONLY THEN, gated by `config.JUDGE_SAMPLE_RATE`, is `judge_answer()`
called synchronously in the same request (spec.md section 10.2) -- the
only way `feedback.source="judge"` rows ever get populated from real
traffic. A judge failure is caught and logged; it must never affect
the already-rendered answer.

`st.session_state` holds the last submitted conversation's id, answer,
and metrics so a feedback-button click (which triggers a Streamlit
rerun) never re-calls `generate_answer()`/`judge_answer()` -- that
would silently duplicate real LLM cost.

Retrieval-layer exceptions from `generate_answer()` (infrastructure
failures, by that function's own documented design) are caught here at
the UI boundary and shown via `st.error`, instead of crashing the whole
Streamlit process.
"""

from __future__ import annotations

import logging
import random

import streamlit as st

from src.config import JUDGE_SAMPLE_RATE
from src.db.monitoring_store import insert_feedback
from src.rag.generator import generate_answer
from src.rag.judge import judge_answer

logger = logging.getLogger(__name__)

__all__ = ["render_qa_panel"]

_SESSION_KEY = "qa_last_result"


def _should_judge(sample_rate: float = JUDGE_SAMPLE_RATE) -> bool:
    """Sampling gate for the live production judge (spec.md section 10.2/12.2)."""
    return random.random() < sample_rate


def _maybe_judge(user_query: str, answer: str, conversation_id: str) -> None:
    """
    Judge dispatch, gated by `_should_judge()`. No `st.*` calls -- kept
    separate from rendering so this logic is unit-testable without a
    running Streamlit script (e.g. `JUDGE_SAMPLE_RATE=0.0` never calls
    `judge_answer()`, `JUDGE_SAMPLE_RATE=1.0` always does).
    """
    if not _should_judge():
        return
    try:
        judge_answer(user_query, answer, conversation_id)
    except Exception:
        logger.error("judge_answer() failed for conversation %s", conversation_id, exc_info=True)


def _handle_feedback(conversation_id: str, score: int) -> None:
    """Persist a user +1/-1 click. No `st.*` calls -- kept separate from the button widget."""
    insert_feedback(conversation_id=conversation_id, source="user", score=score)


def _submit_query(user_query: str) -> None:
    """
    Generate an answer for `user_query`, render it immediately, then
    (sampled) judge it. Stores the result in `st.session_state` so
    later feedback-button reruns can re-render without re-generating.
    """
    with st.spinner("Generating answer..."):
        try:
            generated = generate_answer(user_query)
        except Exception:
            logger.error("generate_answer() failed for query %r", user_query, exc_info=True)
            st.error("Sorry, something went wrong while generating an answer. Please try again.")
            return

    st.session_state[_SESSION_KEY] = {
        "conversation_id": generated.conversation_id,
        "answer": generated.answer,
        "prompt_tokens": generated.prompt_tokens,
        "completion_tokens": generated.completion_tokens,
        "total_tokens": generated.total_tokens,
        "latency_seconds": generated.latency_seconds,
        "cost_usd": generated.cost_usd,
    }

    # Render answer + metrics + feedback buttons FIRST -- the user sees this
    # the instant it runs, before the (potentially slower) judge call below.
    _render_stored_result()
    _maybe_judge(user_query, generated.answer, generated.conversation_id)


def _render_stored_result() -> None:
    """Render the last submitted answer + metrics + feedback buttons, if any."""
    result = st.session_state.get(_SESSION_KEY)
    if result is None:
        return

    st.write(result["answer"])
    st.write(
        {
            "prompt_tokens": result["prompt_tokens"],
            "completion_tokens": result["completion_tokens"],
            "total_tokens": result["total_tokens"],
            "latency_seconds": result["latency_seconds"],
            "cost_usd": result["cost_usd"],
        }
    )

    conversation_id = result["conversation_id"]
    col_up, col_down = st.columns(2)
    if col_up.button("+1 \U0001F44D", key=f"feedback_up_{conversation_id}"):
        _handle_feedback(conversation_id, 1)
        st.success("Thanks for the feedback!")
    if col_down.button("-1 \U0001F44E", key=f"feedback_down_{conversation_id}"):
        _handle_feedback(conversation_id, -1)
        st.success("Thanks for the feedback!")


def render_qa_panel() -> None:
    """Render the Q&A panel: query input, submit button, answer, and feedback buttons."""
    st.header("Ask a MOSFET Selection Question")
    user_query = st.text_input("Your question")
    submitted = st.button("Submit")

    if submitted and user_query.strip():
        _submit_query(user_query)
    else:
        _render_stored_result()
