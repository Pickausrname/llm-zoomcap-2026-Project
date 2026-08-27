"""
LLM (backbone) evaluation -- A -> Q -> A' framework (spec.md section 11.4).

For every usable row of `data/ground_truth.csv` (`question`, `document_id`
-- `document_id` is `master_table.id`, per `generate_ground_truth.py`),
resolves the source answer **A** as `master_table.search_text` (a single
batch join on `document_id`, mirroring `generate_ground_truth.py`'s own
`_fetch_records` pattern), runs the full RAG pipeline
(`src.rag.generator.generate_answer`) to produce **A'** for two LLM
backbones ("openai"/`OPENAI_MODEL`, "gemini"/`GEMINI_MODEL`, both via
`src.llm.factory.get_llm`), and grades each `(Q, A, A')` triple with an
LLM-as-judge (`JudgeVerdict`).

**Cross-grading:** the judge for a given model's answers is always the
OPPOSITE provider (openai's answers judged by gemini and vice versa) --
never same-provider self-grading, to avoid self-preference bias.

**Concurrency:** sequential-per-model, parallel-within-model. All
ground-truth rows for one model run through a single `ThreadPoolExecutor`
batch, which fully completes before the next model's batch starts --
the two models' requests are never interleaved in one shared pool.

**Failure handling:** skip-and-continue, matching every other module's
convention in this repo. A row's `generate_answer()`/judge-call
exception is logged and excluded from that model's accuracy/latency
aggregates (but not silently discarded -- it's counted in that model's
`n_failures`, which doubles as the "reliability" signal for winner
selection). `generate_answer()` itself swallows most LLM-side failures
internally and returns a canned fallback answer instead of raising (see
`rag/generator.py`) -- this module detects that fallback via its public
`GENERATION_FAILURE_MODEL` sentinel and treats it as a row failure too
(skipping the judge call for it), so an LLM outage during an evaluation
run is never silently scored as a normal judged "bad" answer.

**Persistence (sanctioned schema extension, spec.md section 11.4):**
each row's `JudgeVerdict` is persisted to the existing `feedback` table
under a NEW `source="eval_judge"` (never `"judge"`, which is reserved for
`rag/judge.py`'s live production relevance judge -- kept distinct so
offline benchmark runs never blend into a "judge score over time"
dashboard query over real traffic). Each model's aggregated run summary
is additionally persisted to a NEW `llm_eval_runs` table (one row per
`(model, run_timestamp)` per invocation, always INSERTED, never
overwritten) -- the durable history a future "eval score over time" view
would read from, since this module's own JSON/CSV outputs are atomically
overwritten every run. See `src/db/monitoring_store.py`.

**No `src/config.py` write-back:** unlike `evaluate_retrieval.py`
(spec.md section 11.3), this module only reports the winning model
(JSON/CSV + logs) -- a human decides whether to manually update
`DEFAULT_LLM_PROVIDER` afterward. `evaluate_llm()` never touches
`src/config.py`.

**Qualitative failure analysis (spec.md section 11.4):** for every row
judged "bad", a root cause is attributed via a documented heuristic. A'
`GeneratedAnswer` doesn't expose the documents `generate_answer()`
retrieved internally, so this module makes ONE extra
`src.retrieval.pipeline.retrieve()` call -- only for "bad" rows -- to
inspect what was actually retrieved for that question:
  - "missing_context": retrieval returned zero documents.
  - "irrelevant_context": documents were returned, but not the
    ground-truth `document_id` -- retrieval missed the right source.
  - "hallucination": the correct source document WAS retrieved, so the
    bad answer is attributed to generation, not retrieval.
  - "unknown": the diagnostic retrieval call itself failed.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel

from src.config import GROUND_TRUTH_CSV, LLM_EVAL_RESULTS_CSV, LLM_EVAL_RESULTS_JSON
from src.db.knowledge_store import connect as connect_knowledge
from src.db.monitoring_store import insert_feedback, insert_llm_eval_run
from src.llm.factory import get_llm
from src.rag.generator import GENERATION_FAILURE_MODEL, generate_answer
from src.retrieval.pipeline import retrieve

logger = logging.getLogger(__name__)

__all__ = ["JudgeVerdict", "evaluate_llm"]

# The two backbones swapped via src.llm.factory (spec.md section 11.4).
_MODELS: tuple[str, ...] = ("openai", "gemini")

# Cross-grading rule (avoids self-preference bias): a model's answers are
# always judged by the OPPOSITE provider -- never same-provider self-grading.
_JUDGE_PROVIDER: dict[str, str] = {"openai": "gemini", "gemini": "openai"}

# Judgment call (spec.md section 11.4 leaves the verdict->score mapping
# undefined): mirrors rag/judge.py's signed-scale convention.
_VERDICT_TO_SCORE: dict[str, int] = {"good": 1, "bad": -1}

_JUDGE_SYSTEM_PROMPT = (
    "You are grading whether a generated answer (A') is semantically "
    "equivalent to a known-correct source answer (A), in response to a "
    "question (Q). Think step by step about whether A' captures the same "
    "key facts as A relative to Q, then respond:\n"
    "- 'good': A' is factually consistent with A and adequately answers Q.\n"
    "- 'bad': A' contradicts, omits key facts from, or fabricates "
    "information relative to A.\n\n"
    "Always include your step-by-step reasoning."
)


class JudgeVerdict(BaseModel):
    """Structured-output schema for the A/Q/A' judge call (spec.md section 11.4)."""

    verdict: Literal["good", "bad"]
    reasoning: str


@dataclass(frozen=True)
class _UsableRow:
    """One ground-truth row with its source answer A already resolved."""

    question: str
    document_id: int
    source_answer: str


@dataclass
class _RowResult:
    """Everything produced (or attempted) for one `(question, model)` pair."""

    model: str
    question: str
    document_id: int
    judge_provider: str
    conversation_id: str | None = None
    generation_succeeded: bool = False
    verdict: str | None = None
    reasoning: str | None = None
    gen_cost_usd: float = 0.0
    judge_cost_usd: float = 0.0
    latency_seconds: float = 0.0
    failure_stage: str | None = None  # None | "generation" | "judge"
    failure_reason: str | None = None
    failure_category: str | None = None  # only set when verdict == "bad"


def _utcnow_iso() -> str:
    """Timezone-aware UTC timestamp in ISO-8601, shared by every model's run row."""
    return datetime.now(timezone.utc).isoformat()


def _load_ground_truth() -> list[tuple[str, int]]:
    """
    Load `(question, document_id)` pairs from `config.GROUND_TRUTH_CSV`.

    Never raises on missing/empty/malformed input -- logs a warning and
    returns as much (possibly zero) usable data as it can, matching this
    repo's established convention (`generate_ground_truth.py`,
    `evaluate_retrieval.py`).
    """
    try:
        with open(GROUND_TRUTH_CSV, "r", encoding="utf-8", newline="") as f:
            rows: list[tuple[str, int]] = []
            for row in csv.DictReader(f):
                question = (row.get("question") or "").strip()
                raw_id = (row.get("document_id") or "").strip()
                if not question or not raw_id:
                    logger.warning("Skipping malformed ground-truth row: %r", row)
                    continue
                try:
                    document_id = int(raw_id)
                except ValueError:
                    logger.warning(
                        "Skipping ground-truth row with non-numeric document_id: %r", raw_id
                    )
                    continue
                rows.append((question, document_id))
    except FileNotFoundError:
        logger.warning(
            "Ground-truth CSV not found at %s; skipping LLM evaluation.", GROUND_TRUTH_CSV
        )
        return []

    if not rows:
        logger.warning(
            "Ground-truth CSV at %s has no usable rows; skipping LLM evaluation.",
            GROUND_TRUTH_CSV,
        )
    return rows


def _resolve_answers(ground_truth: list[tuple[str, int]]) -> list[_UsableRow]:
    """
    Resolve each row's source answer A = `master_table.search_text`.

    A single batch query (mirrors `generate_ground_truth.py`'s
    `_fetch_records` join pattern) avoids one round-trip per row. Rows
    whose `document_id` has no matching `master_table` row, or whose
    `search_text` is empty/missing, are skipped with a `logger.warning`.
    """
    with connect_knowledge() as conn:
        records = conn.execute("SELECT id, search_text FROM master_table").fetchall()
    search_text_by_id: dict[int, str | None] = {row["id"]: row["search_text"] for row in records}

    usable: list[_UsableRow] = []
    for question, document_id in ground_truth:
        if document_id not in search_text_by_id:
            logger.warning(
                "Skipping ground-truth row: no master_table row for document_id=%s", document_id
            )
            continue
        source_answer = search_text_by_id[document_id]
        if not source_answer or not source_answer.strip():
            logger.warning(
                "Skipping ground-truth row: empty search_text for document_id=%s", document_id
            )
            continue
        usable.append(
            _UsableRow(question=question, document_id=document_id, source_answer=source_answer)
        )
    return usable


def _build_judge_prompt(question: str, source_answer: str, generated_answer: str) -> str:
    """Build the user-turn prompt (Q, A, A') sent to the cross-graded judge LLM."""
    return (
        f"Question (Q): {question}\n\n"
        f"Source answer (A): {source_answer}\n\n"
        f"Generated answer (A'): {generated_answer}"
    )


def _categorize_failure(question: str, target_document_id: int) -> str:
    """
    Root-cause heuristic for a 'bad' verdict (see module docstring).

    `generate_answer()` doesn't expose the documents it retrieved
    internally, so this re-runs retrieval for `question` -- a second,
    documented retrieval call, only paid for "bad"-verdict rows -- and
    classifies the root cause as missing/irrelevant retrieved context
    vs. model hallucination.
    """
    try:
        retrieval_result = retrieve(question)
    except Exception:
        logger.error(
            "Failure-analysis retrieval call failed for question=%r", question, exc_info=True
        )
        return "unknown"

    if not retrieval_result.documents:
        return "missing_context"
    retrieved_ids = {doc.id for doc in retrieval_result.documents}
    if target_document_id not in retrieved_ids:
        return "irrelevant_context"
    return "hallucination"


def _evaluate_row(row: _UsableRow, model: str) -> _RowResult:
    """
    Run one ground-truth row's A -> Q -> A' -> judge flow for `model`.

    Never raises -- any `generate_answer()`/judge-call exception is
    caught, logged, and reflected in the returned `_RowResult`'s
    `failure_stage`/`failure_reason` (skip-and-continue, per the
    module's documented failure-handling convention), so this is safe
    to run as a `ThreadPoolExecutor` task without losing visibility
    into per-row failures.
    """
    judge_provider = _JUDGE_PROVIDER[model]
    result = _RowResult(
        model=model,
        question=row.question,
        document_id=row.document_id,
        judge_provider=judge_provider,
    )

    try:
        generated = generate_answer(row.question, provider=model)
    except Exception as exc:
        logger.error(
            "generate_answer failed for model=%s document_id=%s question=%r",
            model,
            row.document_id,
            row.question,
            exc_info=True,
        )
        result.failure_stage = "generation"
        result.failure_reason = str(exc)
        return result

    result.conversation_id = generated.conversation_id
    result.gen_cost_usd = generated.cost_usd
    result.latency_seconds = generated.latency_seconds

    if generated.model == GENERATION_FAILURE_MODEL:
        # generate_answer() swallows LLM-side failures internally and returns this
        # canned fallback instead of raising (rag/generator.py) -- detect it here so
        # an outage still counts as a row failure (excluded from latency averages,
        # never sent to the judge) instead of being silently judged as a normal answer.
        logger.warning(
            "generate_answer() returned a generation-failure fallback for model=%s "
            "document_id=%s; treating as a row failure.",
            model,
            row.document_id,
        )
        result.failure_stage = "generation"
        result.failure_reason = "LLM generation service unavailable (fallback answer returned)"
        return result

    result.generation_succeeded = True

    prompt = _build_judge_prompt(row.question, row.source_answer, generated.answer)
    try:
        judge_llm = get_llm(judge_provider)
        parsed, judge_response = judge_llm.structured(
            prompt, JudgeVerdict, system=_JUDGE_SYSTEM_PROMPT
        )
    except Exception as exc:
        logger.error(
            "Judge call (provider=%s) failed for model=%s document_id=%s conversation_id=%s",
            judge_provider,
            model,
            row.document_id,
            generated.conversation_id,
            exc_info=True,
        )
        result.failure_stage = "judge"
        result.failure_reason = str(exc)
        return result

    result.judge_cost_usd = judge_response.cost_usd
    result.verdict = parsed.verdict
    result.reasoning = parsed.reasoning

    try:
        insert_feedback(
            conversation_id=generated.conversation_id,
            source="eval_judge",
            score=_VERDICT_TO_SCORE[parsed.verdict],
            label=parsed.verdict,
            explanation=parsed.reasoning,
        )
    except Exception:
        # The verdict itself was already produced (real LLM cost incurred) --
        # a persistence failure doesn't invalidate it for in-memory
        # aggregation, but must be logged so it isn't silently lost.
        logger.error(
            "Failed to persist eval_judge feedback for conversation_id=%s (verdict=%s)",
            generated.conversation_id,
            parsed.verdict,
            exc_info=True,
        )

    if parsed.verdict == "bad":
        result.failure_category = _categorize_failure(row.question, row.document_id)

    return result


def _aggregate_model_results(model: str, rows: list[_RowResult]) -> dict:
    """Aggregate accuracy/cost/latency/failure metrics for one model's batch (spec.md section 11.4)."""
    n_samples = len(rows)
    n_failures = sum(1 for r in rows if r.failure_stage is not None)
    judged = [r for r in rows if r.verdict is not None]
    good_count = sum(1 for r in judged if r.verdict == "good")
    accuracy = good_count / len(judged) if judged else 0.0

    total_cost_usd = sum(r.gen_cost_usd + r.judge_cost_usd for r in rows)

    latencies = [r.latency_seconds for r in rows if r.generation_succeeded]
    avg_latency_seconds = sum(latencies) / len(latencies) if latencies else 0.0

    failure_analysis: dict[str, int] = {}
    for r in judged:
        if r.verdict == "bad" and r.failure_category:
            failure_analysis[r.failure_category] = failure_analysis.get(r.failure_category, 0) + 1

    return {
        "model": model,
        "n_samples": n_samples,
        "n_judged": len(judged),
        "n_failures": n_failures,
        "accuracy": accuracy,
        "total_cost_usd": total_cost_usd,
        "avg_latency_seconds": avg_latency_seconds,
        "failure_analysis": failure_analysis,
        "is_winner": False,
    }


def _select_winner(aggregates: dict[str, dict]) -> tuple[str | None, str | None]:
    """
    Pick the winning model (spec.md section 11.4: "accuracy, cost efficiency,
    and reliability"), ranked highest accuracy first, ties broken by fewer
    failures (reliability), then by lower total cost (cost efficiency).
    """
    if not aggregates:
        return None, None

    def _sort_key(item: tuple[str, dict]) -> tuple[float, int, float]:
        _model, agg = item
        return (-agg["accuracy"], agg["n_failures"], agg["total_cost_usd"])

    ranked = sorted(aggregates.items(), key=_sort_key)
    winner_model, winner_agg = ranked[0]
    reason = (
        f"{winner_model} selected: accuracy={winner_agg['accuracy']:.2%}, "
        f"n_failures={winner_agg['n_failures']}, "
        f"total_cost_usd={winner_agg['total_cost_usd']:.6f} "
        "(ranked by accuracy desc, then failure count asc, then cost asc)"
    )
    return winner_model, reason


def _row_result_to_dict(r: _RowResult) -> dict:
    """Flatten a `_RowResult` into the dict shape written to both JSON and CSV outputs."""
    return {
        "model": r.model,
        "question": r.question,
        "document_id": r.document_id,
        "judge_provider": r.judge_provider,
        "conversation_id": r.conversation_id,
        "verdict": r.verdict,
        "reasoning": r.reasoning,
        "gen_cost_usd": r.gen_cost_usd,
        "judge_cost_usd": r.judge_cost_usd,
        "total_cost_usd": r.gen_cost_usd + r.judge_cost_usd,
        "latency_seconds": r.latency_seconds,
        "failure_stage": r.failure_stage,
        "failure_reason": r.failure_reason,
        "failure_category": r.failure_category,
    }


_CSV_FIELDNAMES: tuple[str, ...] = (
    "model",
    "question",
    "document_id",
    "judge_provider",
    "conversation_id",
    "verdict",
    "reasoning",
    "gen_cost_usd",
    "judge_cost_usd",
    "total_cost_usd",
    "latency_seconds",
    "failure_stage",
    "failure_reason",
    "failure_category",
)


def _write_results_json(payload: dict) -> None:
    """
    Atomically write per-row results + per-model aggregates + the winner
    to `LLM_EVAL_RESULTS_JSON` (tempfile in the same dir + `os.replace`,
    cleaned up on any failure) -- same pattern `evaluate_retrieval.py`
    uses for its own JSON output.
    """
    LLM_EVAL_RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=LLM_EVAL_RESULTS_JSON.parent, prefix=".llm_eval_", suffix=".json.tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp_path, LLM_EVAL_RESULTS_JSON)
    except BaseException:
        os.remove(tmp_path)
        raise


def _write_results_csv(rows: list[dict]) -> None:
    """
    Atomically write the flat per-row detail table to `LLM_EVAL_RESULTS_CSV`
    (per-model aggregates/winner are JSON-only, since they don't fit a flat
    per-row table) -- same tempfile + `os.replace` pattern as the JSON writer.
    """
    LLM_EVAL_RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=LLM_EVAL_RESULTS_CSV.parent, prefix=".llm_eval_", suffix=".csv.tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_FIELDNAMES)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        os.replace(tmp_path, LLM_EVAL_RESULTS_CSV)
    except BaseException:
        os.remove(tmp_path)
        raise


def evaluate_llm() -> dict:
    """
    Run the A -> Q -> A' evaluation (spec.md section 11.4) for both LLM
    backbones against every usable `ground_truth.csv` row, emit per-row +
    aggregated results to JSON/CSV, persist per-row judge verdicts and
    per-model run summaries to the monitoring store, and report (without
    writing back to `config.py`) which model wins.

    If `ground_truth.csv` is missing/empty, or no row's `document_id` has
    a matching `master_table` record, logs a warning and returns
    `{"rows": [], "aggregates": {}, "winner": None, "winner_reason": None}`
    without touching any output artifact or the monitoring store.

    Returns:
        `{"rows": [...], "aggregates": {model: {...}}, "winner": str | None,
        "winner_reason": str | None}`.
    """
    ground_truth = _load_ground_truth()
    if not ground_truth:
        logger.warning("No ground-truth data available; LLM evaluation was not run.")
        return {"rows": [], "aggregates": {}, "winner": None, "winner_reason": None}

    usable_rows = _resolve_answers(ground_truth)
    if not usable_rows:
        logger.warning(
            "No ground-truth row had a matching master_table record; LLM evaluation was not run."
        )
        return {"rows": [], "aggregates": {}, "winner": None, "winner_reason": None}

    run_timestamp = _utcnow_iso()
    all_rows: list[_RowResult] = []
    aggregates: dict[str, dict] = {}

    # Sequential-per-model, parallel-within-model (module docstring): each
    # model's ThreadPoolExecutor batch fully completes before the next
    # model's batch starts -- never interleaved in one shared pool.
    for model in _MODELS:
        logger.info("Starting LLM evaluation batch: model=%s, n_rows=%d", model, len(usable_rows))
        with ThreadPoolExecutor() as executor:
            model_rows = list(executor.map(lambda row, m=model: _evaluate_row(row, m), usable_rows))
        logger.info("Finished LLM evaluation batch: model=%s", model)

        all_rows.extend(model_rows)
        aggregates[model] = _aggregate_model_results(model, model_rows)

    winner, reason = _select_winner(aggregates)
    for model, agg in aggregates.items():
        agg["is_winner"] = model == winner

    for model, agg in aggregates.items():
        try:
            insert_llm_eval_run(
                model=model,
                run_timestamp=run_timestamp,
                accuracy=agg["accuracy"],
                total_cost=agg["total_cost_usd"],
                avg_latency=agg["avg_latency_seconds"],
                n_samples=agg["n_samples"],
                n_failures=agg["n_failures"],
                is_winner=agg["is_winner"],
            )
        except Exception:
            logger.error("Failed to persist llm_eval_runs row for model=%s", model, exc_info=True)

    row_dicts = [_row_result_to_dict(r) for r in all_rows]
    payload = {
        "rows": row_dicts,
        "aggregates": aggregates,
        "winner": winner,
        "winner_reason": reason,
    }
    _write_results_json(payload)
    _write_results_csv(row_dicts)

    logger.info("LLM evaluation complete. Winner: %s -- %s", winner, reason)
    return payload


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    evaluate_llm()
