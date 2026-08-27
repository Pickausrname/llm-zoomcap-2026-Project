"""
Retrieval evaluation & automated winner selection (spec.md sections 11.2/11.3).

Evaluates 4 retrieval configurations against `data/ground_truth.csv`
(`question`, `document_id` -- `document_id` is `master_table.id` as a
string, per `generate_ground_truth.py`):

1. **Approach 1 -- Lexical:** `hybrid_search.lexical_search` (BM25) only.
2. **Approach 2 -- Dense vector:** `hybrid_search.vector_search` (cosine) only.
3. **Approach 3 -- Basic hybrid:** `hybrid_search.hybrid_search(..., use_rrf=True)`
   (Reciprocal Rank Fusion). Spec 11.2 allows RRF *or* weighted fusion for
   this approach; RRF was picked deliberately so Approach 3 (fixed
   fusion, no tuning) is meaningfully distinct from Approach 4 (weighted
   fusion, alpha swept) rather than just being "Approach 4 at one alpha".
4. **Approach 4 -- Hybrid + cross-encoder re-rank, alpha sweep:**
   `hybrid_search.hybrid_search(..., alpha=a)` -> `reranker_stage.rerank`,
   evaluated once per `alpha` in `0.0, 0.1, ..., 1.0` (11 variants).

**Scope decision -- deliberately excludes `query_rewriter.rewrite_query()`:**
Stage 0 (LLM query rewriting) and this evaluation are orthogonal
concerns. Ground-truth questions (spec.md 11.1) are already realistic,
well-formed engineering queries generated for retrieval testing, and
Stage 0/1/2 in spec.md section 9 are described purely as *production*
pipeline stages. Folding an extra LLM call into every one of the ~14
evaluation runs per ground-truth question would add cost/latency/
nondeterminism to what should be a repeatable, deterministic comparison
of the retrieval *algorithms* themselves, without changing the answer to
"which fusion/re-rank configuration retrieves the right document".

**Metrics (spec.md section 11.2), computed over ALL ground-truth rows:**
- **Hit Rate (Recall@5):** fraction of queries where the target
  `document_id` appears anywhere in the top-5 result ids.
- **MRR:** mean of `1/rank` (rank of the target id, 1-based) across
  queries; `0.0` for a query whose target isn't in the top 5.
`config.FINAL_N` (5) is reused as this "top-5" cutoff -- it already
means "how many documents make it into the final retrieval output" in
production, which is exactly the eval semantics spec.md 11.2 wants.

**Winner selection & config.py rewrite (spec.md section 11.3):** highest
MRR, tie-broken on Hit Rate, across all 14 (approach, variant) rows.
`ACTIVE_RETRIEVAL_APPROACH`/`ACTIVE_ALPHA`/`RRF_K` are then rewritten
*in place* in `src/config.py`'s source text (regex/line-based, byte-exact
everywhere else) via the same tempfile + `os.replace` atomic pattern
`generate_ground_truth.py` uses for `ground_truth.csv` -- `config.py` is
imported by every other layer at runtime, so a half-written file would
break the whole application, not just one evaluation artifact.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path

import src.config as _config_module
from src.config import (
    ALPHA,
    APPROACH_HYBRID,
    APPROACH_HYBRID_RERANK,
    APPROACH_LEXICAL,
    APPROACH_VECTOR,
    FINAL_N,
    GROUND_TRUTH_CSV,
    RETRIEVAL_EVAL_RESULTS_CSV,
    RETRIEVAL_EVAL_RESULTS_JSON,
    RRF_K,
    TOP_K,
)
from src.retrieval.hybrid_search import Document, hybrid_search, lexical_search, vector_search
from src.retrieval.reranker_stage import rerank

logger = logging.getLogger(__name__)

__all__ = ["evaluate_retrieval"]

# Alpha values swept for Approach 4, per spec.md 11.2 ("sweep hybrid weight
# alpha from 0.0 -> 1.0"). `round(..., 1)` avoids float noise (e.g. 0.7000000000000001).
_ALPHA_SWEEP: tuple[float, ...] = tuple(round(i * 0.1, 1) for i in range(11))

_CSV_FIELDNAMES: tuple[str, ...] = (
    "approach",
    "variant",
    "alpha",
    "rrf_k",
    "hit_rate",
    "mrr",
    "n_queries",
    "is_winner",
)

# Maps a config.py APPROACH_* *value* back to the identifier name to write
# into config.py's ACTIVE_RETRIEVAL_APPROACH assignment (spec.md 11.3).
_APPROACH_CONST_NAMES: dict[str, str] = {
    APPROACH_LEXICAL: "APPROACH_LEXICAL",
    APPROACH_VECTOR: "APPROACH_VECTOR",
    APPROACH_HYBRID: "APPROACH_HYBRID",
    APPROACH_HYBRID_RERANK: "APPROACH_HYBRID_RERANK",
}

# Matches, per assignment key, the exact line shape currently in config.py:
# `KEY: <type> = <value>` optionally followed by trailing whitespace/comment,
# which is captured (group 3) and preserved verbatim in the rewritten line.
_ASSIGNMENT_PATTERNS: dict[str, re.Pattern[str]] = {
    "ACTIVE_RETRIEVAL_APPROACH": re.compile(r"^(ACTIVE_RETRIEVAL_APPROACH: str = )(\S+)(.*)$"),
    "ACTIVE_ALPHA": re.compile(r"^(ACTIVE_ALPHA: float = )(\S+)(.*)$"),
    "RRF_K": re.compile(r"^(RRF_K: int = )(\d+)(.*)$"),
}


def _load_ground_truth() -> list[tuple[str, int]]:
    """
    Load `(question, document_id)` pairs from `config.GROUND_TRUTH_CSV`.

    Never raises on missing/empty/malformed input -- logs a warning and
    returns as much (possibly zero) usable data as it can, matching this
    repo's "never crash on bad/missing data" convention
    (`pdf_extractor.py`, `generate_ground_truth.py`).
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
            "Ground-truth CSV not found at %s; skipping retrieval evaluation.", GROUND_TRUTH_CSV
        )
        return []

    if not rows:
        logger.warning(
            "Ground-truth CSV at %s has no usable rows; skipping retrieval evaluation.",
            GROUND_TRUTH_CSV,
        )
    return rows


def _hit_and_reciprocal_rank(result_ids: list[int], target_id: int, k: int) -> tuple[bool, float]:
    """Whether `target_id` is among the first `k` of `result_ids`, and its `1/rank` (0.0 if absent)."""
    for rank, doc_id in enumerate(result_ids[:k], start=1):
        if doc_id == target_id:
            return True, 1.0 / rank
    return False, 0.0


def _evaluate_variant(
    approach: str,
    variant: str,
    alpha: float | None,
    rrf_k: int | None,
    search_fn: Callable[[str], list[Document]],
    ground_truth: list[tuple[str, int]],
    k: int,
) -> dict:
    """Run `search_fn` over every ground-truth query and compute Hit Rate@`k` / MRR."""
    hits = 0
    reciprocal_ranks: list[float] = []
    for question, target_id in ground_truth:
        result_ids = [doc.id for doc in search_fn(question)]
        hit, reciprocal_rank = _hit_and_reciprocal_rank(result_ids, target_id, k)
        hits += int(hit)
        reciprocal_ranks.append(reciprocal_rank)

    n_queries = len(ground_truth)
    hit_rate = hits / n_queries
    mrr = sum(reciprocal_ranks) / n_queries
    logger.info(
        "Evaluated approach=%s variant=%s: hit_rate=%.3f mrr=%.3f (n=%d)",
        approach,
        variant,
        hit_rate,
        mrr,
        n_queries,
    )
    return {
        "approach": approach,
        "variant": variant,
        "alpha": alpha,
        "rrf_k": rrf_k,
        "hit_rate": hit_rate,
        "mrr": mrr,
        "n_queries": n_queries,
    }


def _select_winner(results: list[dict]) -> dict:
    """Pick the highest-MRR row, tie-broken on Hit Rate (spec.md 11.3)."""
    return max(results, key=lambda r: (r["mrr"], r["hit_rate"]))


def _write_results_json(results: list[dict], winner: dict) -> None:
    """Atomically write the side-by-side comparison matrix to `RETRIEVAL_EVAL_RESULTS_JSON`."""
    RETRIEVAL_EVAL_RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=RETRIEVAL_EVAL_RESULTS_JSON.parent, prefix=".retrieval_eval_", suffix=".json.tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump({"results": results, "winner": winner}, f, indent=2)
        os.replace(tmp_path, RETRIEVAL_EVAL_RESULTS_JSON)
    except BaseException:
        os.remove(tmp_path)
        raise


def _write_results_csv(results: list[dict]) -> None:
    """Atomically write the side-by-side comparison matrix to `RETRIEVAL_EVAL_RESULTS_CSV`."""
    RETRIEVAL_EVAL_RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=RETRIEVAL_EVAL_RESULTS_CSV.parent, prefix=".retrieval_eval_", suffix=".csv.tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_FIELDNAMES)
            writer.writeheader()
            for row in results:
                writer.writerow(row)
        os.replace(tmp_path, RETRIEVAL_EVAL_RESULTS_CSV)
    except BaseException:
        os.remove(tmp_path)
        raise


def _split_line_ending(line: str) -> tuple[str, str]:
    """Split `line` into `(body, ending)`, where `ending` is `''`, `'\\n'`, `'\\r'`, or `'\\r\\n'`."""
    for ending in ("\r\n", "\n", "\r"):
        if line.endswith(ending):
            return line[: -len(ending)], ending
    return line, ""


def _replace_config_source(source: str, new_values: dict[str, str]) -> str:
    """
    Return `source` with each `ACTIVE_RETRIEVAL_APPROACH`/`ACTIVE_ALPHA`/`RRF_K`
    assignment line's value replaced per `new_values`, leaving every other
    line -- including each replaced line's own trailing comment/whitespace
    and original line ending -- byte-for-byte unchanged.

    Raises `RuntimeError` (rather than silently writing a partial result)
    if any key in `new_values` isn't found, so a future hand-edit of
    config.py that changes these lines' shape fails loudly instead of
    corrupting the file.
    """
    remaining = dict(new_values)
    new_lines: list[str] = []
    for line in source.splitlines(keepends=True):
        body, ending = _split_line_ending(line)
        for key in list(remaining):
            match = _ASSIGNMENT_PATTERNS[key].match(body)
            if match:
                new_lines.append(f"{match.group(1)}{remaining.pop(key)}{match.group(3)}{ending}")
                break
        else:
            new_lines.append(line)
    if remaining:
        raise RuntimeError(
            "Could not locate config.py assignment line(s) for: "
            f"{sorted(remaining)}; aborting write to avoid corrupting the file."
        )
    return "".join(new_lines)


def _write_winner_to_config(approach: str, alpha: float, rrf_k: int) -> None:
    """
    Overwrite `ACTIVE_RETRIEVAL_APPROACH`/`ACTIVE_ALPHA`/`RRF_K` in `src/config.py`
    in place, atomically (tempfile in the same dir + `os.replace`, cleaned up
    on any failure) -- same pattern `generate_ground_truth.py` uses for
    `ground_truth.csv`, needed here because `config.py` is a live source file
    every other layer imports at runtime.
    """
    approach_name = _APPROACH_CONST_NAMES.get(approach)
    if approach_name is None:
        raise ValueError(f"Unrecognized winning approach id: {approach!r}")

    config_path = Path(_config_module.__file__)
    # newline="" on both read and write disables newline translation, so
    # config.py's existing line-ending convention (CRLF) is preserved
    # exactly, including on every untouched line.
    with open(config_path, "r", encoding="utf-8", newline="") as f:
        original = f.read()

    updated = _replace_config_source(
        original,
        {
            "ACTIVE_RETRIEVAL_APPROACH": approach_name,
            "ACTIVE_ALPHA": repr(alpha),
            "RRF_K": str(rrf_k),
        },
    )

    tmp_fd, tmp_path = tempfile.mkstemp(dir=config_path.parent, prefix=".config_", suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="") as f:
            f.write(updated)
        os.replace(tmp_path, config_path)
    except BaseException:
        os.remove(tmp_path)
        raise


def evaluate_retrieval() -> dict:
    """
    Run all 4 retrieval approaches (11.2) against `ground_truth.csv`, emit
    the side-by-side comparison to JSON/CSV, and write the winning
    configuration back into `src/config.py` (11.3).

    If `ground_truth.csv` is missing or has no usable rows, logs a
    warning and returns `{"results": [], "winner": None}` without
    touching the JSON/CSV/`config.py` outputs -- there is nothing
    meaningful to compare or select a winner from, and overwriting
    previously-good evaluation artifacts with an empty result would be
    worse than leaving them untouched. An empty `master_table` needs no
    special handling here: `lexical_search`/`vector_search`/`hybrid_search`
    already return `[]` gracefully for a query with no matching rows
    (see `hybrid_search.py`), which naturally yields `hit_rate=mrr=0.0`
    for every query rather than an exception.

    Infrastructure-level failures (e.g. the knowledge DB/schema not
    existing at all) are deliberately NOT caught here -- consistent with
    `rag/generator.py`'s documented judgment call that retrieval-layer
    outages should propagate rather than be silently masked as a "0 hit
    rate" result.

    Returns:
        `{"results": [...], "winner": {...} | None}` -- `results` is the
        same list of per-approach/variant dicts written to the JSON/CSV
        outputs (each additionally tagged `is_winner`).
    """
    ground_truth = _load_ground_truth()
    if not ground_truth:
        logger.warning("No ground-truth data available; retrieval evaluation was not run.")
        return {"results": [], "winner": None}

    results: list[dict] = []

    results.append(
        _evaluate_variant(
            approach=APPROACH_LEXICAL,
            variant="lexical_bm25",
            alpha=None,
            rrf_k=None,
            search_fn=lambda q: lexical_search(q, top_k=TOP_K),
            ground_truth=ground_truth,
            k=FINAL_N,
        )
    )
    results.append(
        _evaluate_variant(
            approach=APPROACH_VECTOR,
            variant="dense_vector",
            alpha=None,
            rrf_k=None,
            search_fn=lambda q: vector_search(q, top_k=TOP_K),
            ground_truth=ground_truth,
            k=FINAL_N,
        )
    )
    results.append(
        _evaluate_variant(
            approach=APPROACH_HYBRID,
            variant="hybrid_rrf",
            alpha=None,
            rrf_k=RRF_K,
            search_fn=lambda q: hybrid_search(q, top_k=TOP_K, use_rrf=True),
            ground_truth=ground_truth,
            k=FINAL_N,
        )
    )
    for alpha in _ALPHA_SWEEP:
        results.append(
            _evaluate_variant(
                approach=APPROACH_HYBRID_RERANK,
                variant=f"hybrid_rerank_alpha_{alpha:.1f}",
                alpha=alpha,
                rrf_k=None,
                search_fn=lambda q, a=alpha: rerank(
                    q, hybrid_search(q, top_k=TOP_K, alpha=a), final_n=FINAL_N
                ),
                ground_truth=ground_truth,
                k=FINAL_N,
            )
        )

    winner = _select_winner(results)
    for row in results:
        row["is_winner"] = row is winner

    _write_results_json(results, winner)
    _write_results_csv(results)

    winner_alpha = winner["alpha"] if winner["alpha"] is not None else ALPHA
    winner_rrf_k = winner["rrf_k"] if winner["rrf_k"] is not None else RRF_K
    _write_winner_to_config(winner["approach"], winner_alpha, winner_rrf_k)

    logger.info(
        "Retrieval evaluation winner: approach=%s variant=%s hit_rate=%.3f mrr=%.3f "
        "(alpha=%s, rrf_k=%s written to config.py).",
        winner["approach"],
        winner["variant"],
        winner["hit_rate"],
        winner["mrr"],
        winner_alpha,
        winner_rrf_k,
    )
    return {"results": results, "winner": winner}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    evaluate_retrieval()
