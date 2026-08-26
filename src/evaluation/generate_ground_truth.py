"""
Ground truth generation for retrieval/RAG evaluation (spec.md section 11.1).

For every record in `master_table`, asks an LLM (via
`src.llm.factory.get_llm(...).structured()`) to generate ~5 realistic
engineering queries that a user might type to find that record, then
writes `data/ground_truth.csv` (`question`, `document_id`) --
`document_id` is `master_table.id`, the stable link that
`evaluate_retrieval.py`/`evaluate_llm.py` join back on.

No `answer` column is written here: `evaluate_llm.py` resolves the
source answer `A` itself at evaluation time via
`SELECT search_text FROM master_table WHERE id = ?`, keyed on
`document_id` -- see /memories/repo/project-notes.md for the resolved
design discussion.
"""

from __future__ import annotations

import csv
import logging
import os
import sqlite3
import tempfile

from pydantic import BaseModel

from src.config import GROUND_TRUTH_CSV
from src.db.knowledge_store import connect
from src.llm.factory import get_llm

logger = logging.getLogger(__name__)

__all__ = ["Questions", "generate_ground_truth"]

_SYSTEM_PROMPT = (
    "You are simulating a hardware engineer searching a MOSFET datasheet "
    "database. Given the extracted datasheet text for one specific MOSFET "
    "part below, write about 5 realistic, varied engineering search "
    "queries a user might type to find this exact part -- e.g. based on "
    "its electrical ratings, switching characteristics, package type, "
    "RoHS/compliance, or intended applications. Do not mention the part "
    "number or manufacturer name directly in the queries; phrase them the "
    "way someone searching by requirements (not by name) would."
)


class Questions(BaseModel):
    """Structured-output schema for the ground-truth question-generation call."""

    questions: list[str]


def _fetch_records(conn: sqlite3.Connection) -> list[tuple[int, str | None]]:
    """Return `(id, search_text)` for every row in `master_table`."""
    rows = conn.execute("SELECT id, search_text FROM master_table").fetchall()
    return [(row["id"], row["search_text"]) for row in rows]


def generate_ground_truth(provider: str | None = None) -> int:
    """
    Regenerate `data/ground_truth.csv` from every `master_table` record.

    For each record with non-empty `search_text`, asks the LLM for ~5
    realistic search queries and writes one CSV row per question
    (`question`, `document_id=master_table.id`). Records with empty/
    missing `search_text` (extraction failures at ingestion time, spec.md
    section 8.5) are skipped with a `logger.warning` -- one bad record
    must never abort the whole run, matching
    `src.ingestion.pdf_extractor`/`resources`'s existing philosophy.

    Likewise, if a single record's `.structured()` call fails (rate
    limit, provider outage, parse failure), that record is skipped (with
    `logger.error(..., exc_info=True)`) and generation continues with the
    next record -- this runs once, offline, sequentially over the whole
    table, so there is no batch/executor to lose partial progress to.

    Overwrites `data/ground_truth.csv` on every run -- this is a full
    regeneration of the ground-truth set, not an append. The file is
    replaced atomically (written to a temp file, then `os.replace`d in)
    only once every record has been processed, so a crash partway through
    never leaves a truncated CSV in the target's place.

    Args:
        provider: Optional LLM provider override (`"openai"`/`"gemini"`),
            forwarded to `src.llm.factory.get_llm`. Defaults to
            `config.DEFAULT_LLM_PROVIDER` when omitted.

    Returns:
        The number of question rows written to `ground_truth.csv`.
    """
    with connect() as conn:
        records = _fetch_records(conn)

    rows_written = 0
    GROUND_TRUTH_CSV.parent.mkdir(parents=True, exist_ok=True)

    # Write to a sibling temp file and atomically replace the target only on
    # full success, so a mid-run crash (LLM outage, disk error, interrupt)
    # never leaves a truncated CSV masquerading as a complete ground-truth
    # set -- the previous file is untouched until every record is processed.
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=GROUND_TRUTH_CSV.parent, prefix=".ground_truth_", suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["question", "document_id"])

            for document_id, search_text in records:
                if not search_text or not search_text.strip():
                    logger.warning(
                        "Skipping master_table.id=%s: empty/missing search_text.",
                        document_id,
                    )
                    continue

                try:
                    llm = get_llm(provider)
                    parsed, _response = llm.structured(
                        search_text, Questions, system=_SYSTEM_PROMPT
                    )
                except Exception:
                    logger.error(
                        "Skipping master_table.id=%s: question generation failed.",
                        document_id,
                        exc_info=True,
                    )
                    continue

                for question in parsed.questions:
                    question = question.strip()
                    if not question:
                        continue
                    writer.writerow([question, document_id])
                    rows_written += 1
        os.replace(tmp_path, GROUND_TRUTH_CSV)
    except BaseException:
        os.remove(tmp_path)
        raise

    logger.info(
        "Wrote %d ground-truth rows from %d master_table records to %s.",
        rows_written,
        len(records),
        GROUND_TRUTH_CSV,
    )
    return rows_written


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    generate_ground_truth()
