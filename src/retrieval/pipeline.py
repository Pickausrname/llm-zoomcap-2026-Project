"""
Public retrieval entrypoint (spec.md section 9).

Orchestrates the full retrieval flow: Stage 0 query rewriting
(`query_rewriter.rewrite_query`) -> Stage 1 hybrid search
(`hybrid_search.hybrid_search`) -> Stage 2 cross-encoder re-ranking
(`reranker_stage.rerank`). This is the single function the RAG
generator (spec.md section 10) and the retrieval evaluation harness
(spec.md section 11) call to fetch context documents for a query.

Reads `config.ACTIVE_RETRIEVAL_APPROACH` to decide which stages
actually run (spec.md sections 4.2/11.3: "the production retrieval
pipeline reads these values" once offline evaluation picks a winner),
so this is the one place in the package that branches on it.

Holds no module-level mutable state; every stage it calls is itself
safe under concurrent `ThreadPoolExecutor` use (spec.md section 11.4).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.config import (
    ACTIVE_RETRIEVAL_APPROACH,
    APPROACH_HYBRID,
    APPROACH_HYBRID_RERANK,
    APPROACH_LEXICAL,
    APPROACH_VECTOR,
    FINAL_N,
)
from src.retrieval.hybrid_search import Document, hybrid_search, lexical_search, vector_search
from src.retrieval.query_rewriter import rewrite_query
from src.retrieval.reranker_stage import rerank

logger = logging.getLogger(__name__)

__all__ = ["RetrievalResult", "retrieve"]

_KNOWN_APPROACHES = frozenset(
    {APPROACH_LEXICAL, APPROACH_VECTOR, APPROACH_HYBRID, APPROACH_HYBRID_RERANK}
)


@dataclass(frozen=True)
class RetrievalResult:
    """
    Bundles Stage 0's rewritten query with the final retrieved documents.

    `rag/generator.py` needs the rewritten query (not just the final
    documents) to populate `monitoring_store.insert_conversation()`'s
    `rewritten_query` column, hence this wrapper instead of a bare
    `list[Document]`. Frozen for the same cross-thread-safety rationale
    as `Document` itself.
    """

    rewritten_query: str
    documents: list[Document]


def retrieve(user_query: str) -> RetrievalResult:
    """
    Run the retrieval pipeline for `user_query`.

    Stage 0 (query rewriting) always runs. Which of Stage 1's lexical/
    vector/hybrid search and Stage 2's cross-encoder re-rank run is
    selected by `config.ACTIVE_RETRIEVAL_APPROACH`, so this function's
    behavior updates automatically whenever that constant is changed --
    no code change needed here.

    Args:
        user_query: The raw natural-language query as typed by the user.

    Returns:
        A `RetrievalResult` bundling the Stage 0 rewritten query with up
        to `config.FINAL_N` `Document`s, sorted descending by relevance
        -- ready to inject into the LLM generation context.
    """
    rewritten_query = rewrite_query(user_query)
    logger.info("Query rewritten: %r -> %r", user_query, rewritten_query)

    approach = ACTIVE_RETRIEVAL_APPROACH
    if approach not in _KNOWN_APPROACHES:
        logger.warning(
            "Unrecognized ACTIVE_RETRIEVAL_APPROACH %r; defaulting to %s.",
            approach,
            APPROACH_HYBRID_RERANK,
        )
        approach = APPROACH_HYBRID_RERANK

    if approach == APPROACH_LEXICAL:
        results = lexical_search(rewritten_query, top_k=FINAL_N)
    elif approach == APPROACH_VECTOR:
        results = vector_search(rewritten_query, top_k=FINAL_N)
    else:
        candidates = hybrid_search(rewritten_query)
        logger.info("Stage 1 hybrid search returned %d candidates", len(candidates))
        if approach == APPROACH_HYBRID:
            results = candidates[:FINAL_N]
        else:
            results = rerank(rewritten_query, candidates)

    logger.info("Retrieval approach %r returned %d final documents", approach, len(results))
    return RetrievalResult(rewritten_query=rewritten_query, documents=results)
