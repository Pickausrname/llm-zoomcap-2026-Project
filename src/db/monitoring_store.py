"""
Monitoring/telemetry storage layer for the MOSFET Selection RAG application.

Owns the SQLite-backed monitoring store (``data/monitoring.db``): schema
creation for the ``conversations`` table (one row per RAG query/answer,
with token/latency/cost metrics) and the ``feedback`` table (user +1/-1
clicks and LLM-judge verdicts, FOREIGN KEY-linked to ``conversations``).
It also exposes the connection-management helpers and writer functions
used by the RAG generator, the LLM judge, and the Streamlit Q&A panel.

This module is intentionally limited to connection management, schema
initialization, and inserting rows. Aggregation/reporting queries for
the monitoring dashboard live in ``src/app/dashboard.py``, not here.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from src.config import MONITORING_DB

logger = logging.getLogger(__name__)

__all__ = [
    "get_connection",
    "connect",
    "init_db",
    "insert_conversation",
    "insert_feedback",
    "insert_llm_eval_run",
]

# Special SQLite DSN for an ephemeral, on-disk-free database (tests, etc.).
_MEMORY_DB: Final[str] = ":memory:"

# "eval_judge" (spec.md section 11.4, evaluation/evaluate_llm.py) is a
# DISTINCT source from "judge" (spec.md section 10.2, rag/judge.py's live
# production relevance judge) -- kept separate so an offline A/Q/A' benchmark
# run never blends into a "judge score over time" dashboard query over real
# production traffic. See /memories/repo/project-notes.md for the rationale.
_VALID_FEEDBACK_SOURCES: Final[frozenset[str]] = frozenset({"user", "judge", "eval_judge"})

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_CREATE_CONVERSATIONS_TABLE_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS conversations (
    id                TEXT PRIMARY KEY,
    query             TEXT NOT NULL,
    rewritten_query   TEXT,
    answer            TEXT NOT NULL,
    prompt            TEXT NOT NULL,
    model             TEXT NOT NULL,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    total_tokens      INTEGER,
    response_time     REAL,
    cost              REAL,
    timestamp         TEXT NOT NULL
);
"""

# `conversation_id` cascades on delete so a purged conversation never
# leaves orphaned feedback rows behind (same FK pattern as
# db/knowledge_store.py's future component-attribute tables).
_CREATE_FEEDBACK_TABLE_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS feedback (
    id              INTEGER PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    source          TEXT NOT NULL CHECK (source IN ('user', 'judge', 'eval_judge')),
    score           INTEGER,
    label           TEXT,
    explanation     TEXT,
    timestamp       TEXT NOT NULL
);
"""

_CREATE_FEEDBACK_INDEX_SQL: Final[str] = """
CREATE INDEX IF NOT EXISTS idx_feedback_conversation_id
    ON feedback (conversation_id);
"""

# One row per (model, run_timestamp) per `make eval-llm` invocation (spec.md
# section 11.4). Rows are always INSERTED, never overwritten/upserted -- this
# is the durable history backing a future "eval score over time" view, unlike
# evaluate_llm.py's own JSON/CSV outputs, which are atomically overwritten on
# every run (correct for "current result", useless for trend history).
_CREATE_LLM_EVAL_RUNS_TABLE_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS llm_eval_runs (
    id            INTEGER PRIMARY KEY,
    model         TEXT NOT NULL,
    run_timestamp TEXT NOT NULL,
    accuracy      REAL NOT NULL,
    total_cost    REAL NOT NULL,
    avg_latency   REAL NOT NULL,
    n_samples     INTEGER NOT NULL,
    n_failures    INTEGER NOT NULL,
    is_winner     INTEGER NOT NULL CHECK (is_winner IN (0, 1))
);
"""


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

def get_connection(db_path: str | Path = MONITORING_DB) -> sqlite3.Connection:
    """
    Open a fully configured connection to the monitoring store.

    Configures the connection with row access by column name,
    foreign-key enforcement (for the ``feedback`` -> ``conversations``
    link), and WAL journaling (safer for the concurrent Streamlit/RAG-
    generator/evaluation access patterns of this project).

    Args:
        db_path: Path to the monitoring store SQLite file. Defaults to
            ``config.MONITORING_DB``. Pass ``":memory:"`` for an
            ephemeral in-memory database (useful in tests).

    Returns:
        A ready-to-use ``sqlite3.Connection``. The caller owns the
        connection and must close it (or use :func:`connect` instead).
    """
    if str(db_path) != _MEMORY_DB:
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    # WAL still serializes writers; without this, a second concurrent writer
    # (e.g. ThreadPoolExecutor evaluation runs) fails immediately instead of
    # waiting for the first short-lived insert transaction to commit.
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


@contextmanager
def connect(db_path: str | Path = MONITORING_DB) -> Iterator[sqlite3.Connection]:
    """
    Context-managed monitoring store connection that closes itself.

    Args:
        db_path: Path to the monitoring store SQLite file. Defaults to
            ``config.MONITORING_DB``.

    Yields:
        A ready-to-use ``sqlite3.Connection``, closed automatically on
        exit (including on exception).

    Example:
        >>> with connect() as conn:
        ...     conn.execute("SELECT COUNT(*) FROM conversations").fetchone()
    """
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------

def init_db(db_path: str | Path = MONITORING_DB) -> None:
    """
    Create the monitoring store file (if needed) and apply the full schema.

    Creates the ``conversations`` table, the ``feedback`` table, and a
    lookup index on ``feedback.conversation_id``. Every statement uses
    ``IF NOT EXISTS``, so this function is idempotent and safe to call
    on every application startup.

    Args:
        db_path: Path to the monitoring store SQLite file. Defaults to
            ``config.MONITORING_DB``.
    """
    with connect(db_path) as conn:
        conn.execute(_CREATE_CONVERSATIONS_TABLE_SQL)
        conn.execute(_CREATE_FEEDBACK_TABLE_SQL)
        conn.execute(_CREATE_FEEDBACK_INDEX_SQL)
        conn.execute(_CREATE_LLM_EVAL_RUNS_TABLE_SQL)
        conn.commit()

    logger.info("Monitoring store schema initialized at %s", db_path)


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def _utcnow_iso() -> str:
    """Timezone-aware UTC timestamp in ISO-8601 (spec.md section 5.3/12.1)."""
    return datetime.now(timezone.utc).isoformat()


def insert_conversation(
    query: str,
    answer: str,
    prompt: str,
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
    response_time: float,
    cost: float,
    rewritten_query: str | None = None,
    db_path: str | Path = MONITORING_DB,
) -> str:
    """
    Insert a new conversation record.

    Generates the conversation id (UUID4) and timezone-aware UTC
    timestamp internally, so callers (``rag/generator.py``) only need to
    supply the query/answer/metrics. Opens and closes its own
    connection, making this safe to call concurrently from multiple
    threads (e.g. ``ThreadPoolExecutor`` evaluation runs).

    Args:
        query: Raw user query.
        answer: LLM-generated answer.
        prompt: Full prompt text sent to the LLM.
        model: Model used for generation.
        prompt_tokens: Prompt token count (nullable if unavailable).
        completion_tokens: Completion token count (nullable if unavailable).
        total_tokens: Total token count (nullable if unavailable).
        response_time: Latency in seconds.
        cost: Estimated cost in USD.
        rewritten_query: Stage 0 query-rewrite output, if any.
        db_path: Path to the monitoring store SQLite file. Defaults to
            ``config.MONITORING_DB``.

    Returns:
        The generated conversation id.
    """
    conversation_id = str(uuid.uuid4())
    timestamp = _utcnow_iso()

    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO conversations (
                id, query, rewritten_query, answer, prompt, model,
                prompt_tokens, completion_tokens, total_tokens,
                response_time, cost, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                conversation_id,
                query,
                rewritten_query,
                answer,
                prompt,
                model,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                response_time,
                cost,
                timestamp,
            ),
        )
        conn.commit()

    return conversation_id


def insert_feedback(
    conversation_id: str,
    source: str,
    score: int | None = None,
    label: str | None = None,
    explanation: str | None = None,
    db_path: str | Path = MONITORING_DB,
) -> int:
    """
    Insert a new feedback record linked to an existing conversation.

    Generates the timezone-aware UTC timestamp internally. Opens and
    closes its own connection, making this safe to call concurrently
    from multiple threads/processes (``qa_panel.py`` user clicks,
    ``rag/judge.py`` verdicts).

    Args:
        conversation_id: FOREIGN KEY into ``conversations.id``.
        source: ``"user"``, ``"judge"`` (live production relevance judge,
            spec.md section 10.2), or ``"eval_judge"`` (offline A/Q/A'
            benchmark judge, spec.md section 11.4 -- kept distinct from
            ``"judge"`` so the two never blend in a dashboard query).
        score: ``+1``/``-1`` for user feedback, or a mapped numeric
            value for judge/eval_judge feedback. Nullable.
        label: Judge verdict (``RELEVANT``/``PARTLY_RELEVANT``/
            ``NON_RELEVANT`` for ``"judge"``; ``"good"``/``"bad"`` for
            ``"eval_judge"``). Nullable, unused for user feedback.
        explanation: Judge reasoning. Nullable, unused for user feedback.
        db_path: Path to the monitoring store SQLite file. Defaults to
            ``config.MONITORING_DB``.

    Returns:
        The autoincremented id of the new feedback row.

    Raises:
        ValueError: If ``source`` is not one of ``"user"``/``"judge"``/
            ``"eval_judge"``.
    """
    if source not in _VALID_FEEDBACK_SOURCES:
        raise ValueError(
            f"source must be one of {sorted(_VALID_FEEDBACK_SOURCES)!r}, got {source!r}"
        )

    timestamp = _utcnow_iso()

    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO feedback (
                conversation_id, source, score, label, explanation, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?);
            """,
            (conversation_id, source, score, label, explanation, timestamp),
        )
        conn.commit()
        feedback_id = cursor.lastrowid

    if feedback_id is None:
        # Should be unreachable (INSERT always assigns a rowid); guard survives `python -O`.
        raise RuntimeError("Failed to retrieve autoincremented feedback_id from SQLite insert.")
    return feedback_id


def insert_llm_eval_run(
    model: str,
    run_timestamp: str,
    accuracy: float,
    total_cost: float,
    avg_latency: float,
    n_samples: int,
    n_failures: int,
    is_winner: bool,
    db_path: str | Path = MONITORING_DB,
) -> int:
    """
    Insert one ``llm_eval_runs`` row (spec.md section 11.4).

    One row per ``(model, run_timestamp)`` per ``evaluate_llm.py``
    (``make eval-llm``) invocation. Rows are always INSERTED, never
    overwritten/upserted -- this table is the durable run history
    backing a future "eval score over time" view, unlike
    ``evaluate_llm.py``'s own JSON/CSV outputs, which are atomically
    overwritten on every run. Opens and closes its own connection,
    making this safe to call concurrently from multiple threads.

    Args:
        model: The LLM provider evaluated (``"openai"``/``"gemini"``).
        run_timestamp: Timezone-aware UTC ISO-8601 timestamp shared by
            every model's row from the same evaluation run.
        accuracy: Fraction (0.0-1.0) of judged answers verdicted "good".
        total_cost: Total USD cost (generation + judge calls) for this
            model's run.
        avg_latency: Mean generation ``latency_seconds`` across
            successfully generated rows.
        n_samples: Number of ground-truth rows attempted for this model.
        n_failures: Number of rows where generation or judging raised.
        is_winner: Whether this model was selected as the run's winner.
        db_path: Path to the monitoring store SQLite file. Defaults to
            ``config.MONITORING_DB``.

    Returns:
        The autoincremented id of the new ``llm_eval_runs`` row.
    """
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO llm_eval_runs (
                model, run_timestamp, accuracy, total_cost, avg_latency,
                n_samples, n_failures, is_winner
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                model,
                run_timestamp,
                accuracy,
                total_cost,
                avg_latency,
                n_samples,
                n_failures,
                int(is_winner),
            ),
        )
        conn.commit()
        run_id = cursor.lastrowid

    if run_id is None:
        # Should be unreachable (INSERT always assigns a rowid); guard survives `python -O`.
        raise RuntimeError("Failed to retrieve autoincremented id from llm_eval_runs insert.")
    return run_id


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
