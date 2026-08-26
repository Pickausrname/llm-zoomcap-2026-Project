"""
Stage 1 -- Hybrid search (spec.md section 9.2).

Runs SQLite FTS5 BM25 lexical search over `search_text` (`master_fts`)
and cosine-similarity vector search over `search_vector`
(`master_vec`, via `sqlite-vec`), min-max normalizes each score list to
`[0, 1]`, and fuses them -- either with the mandatory weighted formula
(`final_score = alpha * vector_score + (1 - alpha) * keyword_score`) or
with Reciprocal Rank Fusion (`score = sum(1 / (k + rank_i))`) as an
alternate strategy.

Also defines `Document`, the shared result type produced here and
consumed by `reranker_stage.py` and `pipeline.py`.

Every public function opens its own short-lived `sqlite3.Connection`
(via `src.db.knowledge_store.connect`) and holds no module-level
mutable state, so this module is safe to call concurrently from
multiple threads (spec.md section 11.4, `ThreadPoolExecutor` batch
evaluation).
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass, replace

import sqlite_vec

from src.config import ACTIVE_ALPHA, RRF_K, TOP_K
from src.db.knowledge_store import connect
from src.models_onnx.embedder import embed

logger = logging.getLogger(__name__)

__all__ = [
    "Document",
    "lexical_search",
    "vector_search",
    "fuse_weighted",
    "fuse_rrf",
    "hybrid_search",
]


@dataclass(frozen=True)
class Document:
    """
    A `master_table` row plus a retrieval relevance score.

    Frozen (immutable) so instances can be freely passed between
    pipeline stages -- and across `ThreadPoolExecutor` worker threads --
    without risk of one caller's mutation affecting another's view of
    the same object. Stage transitions that need to change `score`
    build a new instance via `dataclasses.replace`.
    """

    id: int
    component_type: str
    manufacturer_name: str
    part_number: str
    search_text: str
    score: float = 0.0


# Matches the `unicode61` tokenizer's notion of a token closely enough to
# build a safe FTS5 MATCH string: quoting every token means reserved FTS5
# query characters in free text (e.g. "-", '"', ":") can never be
# misinterpreted as query syntax or raise a parse error.
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _to_fts_match_query(text: str) -> str | None:
    """
    Build an OR-of-quoted-tokens FTS5 MATCH string from free text.

    Returns `None` if `text` has no matchable tokens (e.g. empty, or
    punctuation/symbols only) -- an empty MATCH string (`'""'`) is a
    syntax error in SQLite FTS5, so callers must short-circuit instead.
    """
    tokens = _WORD_RE.findall(text)
    if not tokens:
        return None
    return " OR ".join(f'"{token}"' for token in tokens)


def _minmax_normalize(scores: dict[int, float]) -> dict[int, float]:
    """
    Min-max normalize `scores` (id -> raw score) to `[0, 1]`.

    If every score is equal (including the single-candidate case), all
    candidates are treated as equally maximal (normalized to `1.0`)
    since there is no basis to differentiate them.
    """
    if not scores:
        return {}
    values = scores.values()
    lo, hi = min(values), max(values)
    if hi == lo:
        return {doc_id: 1.0 for doc_id in scores}
    span = hi - lo
    return {doc_id: (value - lo) / span for doc_id, value in scores.items()}


def _fetch_documents(conn: sqlite3.Connection, ids: list[int]) -> dict[int, Document]:
    """Fetch `master_table` rows for `ids`, as `Document`s with `score=0.0`."""
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(
        "SELECT id, component_type, manufacturer_name, part_number, search_text "
        f"FROM master_table WHERE id IN ({placeholders})",
        ids,
    ).fetchall()
    return {
        row["id"]: Document(
            id=row["id"],
            component_type=row["component_type"],
            manufacturer_name=row["manufacturer_name"],
            part_number=row["part_number"],
            search_text=row["search_text"],
        )
        for row in rows
    }


def _to_scored_documents(
    documents: dict[int, Document], scores: dict[int, float]
) -> list[Document]:
    """Attach `scores` to `documents` and return them sorted descending by score."""
    scored = [
        replace(documents[doc_id], score=score)
        for doc_id, score in scores.items()
        if doc_id in documents
    ]
    scored.sort(key=lambda doc: doc.score, reverse=True)
    return scored


def lexical_search(query_text: str, top_k: int = TOP_K) -> list[Document]:
    """
    BM25 keyword search over `master_table.search_text` (`master_fts`).

    Args:
        query_text: Free-text query (typically Stage 0's rewritten query).
        top_k: Maximum number of candidates to return. Defaults to `config.TOP_K`.

    Returns:
        Up to `top_k` `Document`s, `score` min-max normalized to `[0, 1]`
        (higher is more relevant), sorted descending by `score`.
    """
    match_query = _to_fts_match_query(query_text)
    if match_query is None:
        logger.debug("No FTS5-matchable tokens in query text: %r", query_text)
        return []

    with connect() as conn:
        rows = conn.execute(
            "SELECT rowid AS id, bm25(master_fts) AS raw_score "
            "FROM master_fts WHERE search_text MATCH ? "
            "ORDER BY raw_score LIMIT ?",
            (match_query, top_k),
        ).fetchall()
        if not rows:
            return []
        # FTS5's bm25() is "lower is better"; negate so higher == more relevant,
        # matching the convention used for vector similarity below.
        raw_scores = {row["id"]: -row["raw_score"] for row in rows}
        documents = _fetch_documents(conn, list(raw_scores))
    return _to_scored_documents(documents, _minmax_normalize(raw_scores))


def vector_search(query_text: str, top_k: int = TOP_K) -> list[Document]:
    """
    Cosine-similarity vector search over `master_table.search_vector` (`master_vec`).

    Args:
        query_text: Free-text query (typically Stage 0's rewritten query),
            embedded here via `src.models_onnx.embedder.embed`.
        top_k: Maximum number of candidates to return. Defaults to `config.TOP_K`.

    Returns:
        Up to `top_k` `Document`s, `score` min-max normalized to `[0, 1]`
        (higher is more relevant), sorted descending by `score`.
    """
    (query_vector,) = embed([query_text])
    serialized_query = sqlite_vec.serialize_float32(query_vector.tolist())
    with connect() as conn:
        # `k` must be a literal for vec0's query planner (it is not a plain
        # WHERE constraint); safe here since `top_k` is always our own int,
        # never raw user input.
        rows = conn.execute(
            "SELECT id, distance FROM master_vec "
            f"WHERE search_vector MATCH ? AND k = {int(top_k)} "
            "ORDER BY distance",
            (serialized_query,),
        ).fetchall()
        if not rows:
            return []
        # `master_vec` uses the default (L2) distance metric, and every stored
        # vector is L2-normalized by embedder.embed(). For unit vectors,
        # cosine_similarity = 1 - (l2_distance ** 2) / 2.
        raw_scores = {row["id"]: 1.0 - (row["distance"] ** 2) / 2.0 for row in rows}
        documents = _fetch_documents(conn, list(raw_scores))
    return _to_scored_documents(documents, _minmax_normalize(raw_scores))


def fuse_weighted(
    vector_scores: dict[int, float],
    keyword_scores: dict[int, float],
    alpha: float = ACTIVE_ALPHA,
) -> dict[int, float]:
    """
    Weighted fusion (spec.md section 9.2, mandatory formula).

    `final_score = alpha * vector_score + (1 - alpha) * keyword_score`.
    A document missing from one of the two inputs is treated as having a
    `0.0` score in that list.

    Args:
        vector_scores: `{doc_id: normalized_vector_score}`.
        keyword_scores: `{doc_id: normalized_keyword_score}`.
        alpha: Fusion weight. Defaults to `config.ACTIVE_ALPHA`.

    Returns:
        `{doc_id: final_score}` for the union of both input id sets.
    """
    doc_ids = set(vector_scores) | set(keyword_scores)
    return {
        doc_id: alpha * vector_scores.get(doc_id, 0.0)
        + (1 - alpha) * keyword_scores.get(doc_id, 0.0)
        for doc_id in doc_ids
    }


def fuse_rrf(ranked_id_lists: list[list[int]], k: int = RRF_K) -> dict[int, float]:
    """
    Reciprocal Rank Fusion (spec.md section 9.2, alternate strategy).

    `score = sum(1 / (k + rank_i))` over every ranked list a document
    appears in, where `rank_i` is its 1-based rank within that list.

    Args:
        ranked_id_lists: One or more lists of document ids, each already
            sorted best-to-worst (e.g. lexical and vector search results).
        k: RRF constant. Defaults to `config.RRF_K`.

    Returns:
        `{doc_id: rrf_score}` for the union of ids across all lists.
    """
    scores: dict[int, float] = {}
    for ranked_ids in ranked_id_lists:
        for rank, doc_id in enumerate(ranked_ids, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return scores


def hybrid_search(
    rewritten_query: str,
    top_k: int = TOP_K,
    alpha: float | None = None,
    use_rrf: bool = False,
    rrf_k: int = RRF_K,
) -> list[Document]:
    """
    Stage 1 hybrid search: fuse lexical BM25 and vector cosine search.

    Args:
        rewritten_query: Stage 0's rewritten search query.
        top_k: Candidates to request from -- and return after fusing --
            each of the lexical/vector searches. Defaults to `config.TOP_K`.
        alpha: Weighted-fusion weight (see `fuse_weighted`). Ignored if
            `use_rrf` is `True`. Defaults to `config.ACTIVE_ALPHA`.
        use_rrf: If `True`, fuse with Reciprocal Rank Fusion (`fuse_rrf`)
            instead of the weighted formula.
        rrf_k: RRF constant, only used when `use_rrf` is `True`. Defaults
            to `config.RRF_K`.

    Returns:
        Up to `top_k` `Document`s, sorted descending by fused `score`.
    """
    lexical_docs = lexical_search(rewritten_query, top_k=top_k)
    vector_docs = vector_search(rewritten_query, top_k=top_k)
    documents = {doc.id: doc for doc in (*lexical_docs, *vector_docs)}

    if use_rrf:
        fused_scores = fuse_rrf(
            [[doc.id for doc in vector_docs], [doc.id for doc in lexical_docs]],
            k=rrf_k,
        )
    else:
        effective_alpha = ACTIVE_ALPHA if alpha is None else alpha
        fused_scores = fuse_weighted(
            vector_scores={doc.id: doc.score for doc in vector_docs},
            keyword_scores={doc.id: doc.score for doc in lexical_docs},
            alpha=effective_alpha,
        )

    return _to_scored_documents(documents, fused_scores)[:top_k]
