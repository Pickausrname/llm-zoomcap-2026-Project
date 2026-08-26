"""
Stage 2 -- Cross-encoder re-ranking (spec.md section 9.3).

Scores each `(query, document)` pair from Stage 1 hybrid search with the
ONNX cross-encoder (`src.models_onnx.reranker.score`), sorts descending
by relevance, and returns the top `config.FINAL_N` documents -- the
final retrieval output injected into the LLM generation context.

Holds no module-level mutable state (the underlying ONNX session cache
in `src.models_onnx.reranker` is itself thread-safe), so this module is
safe to call concurrently from multiple threads (spec.md section 11.4).
"""

from __future__ import annotations

import logging
from dataclasses import replace

from src.config import FINAL_N
from src.models_onnx.reranker import score
from src.retrieval.hybrid_search import Document

logger = logging.getLogger(__name__)

__all__ = ["rerank"]


def rerank(query: str, candidates: list[Document], final_n: int = FINAL_N) -> list[Document]:
    """
    Cross-encoder re-rank `candidates` for `query`, returning the top `final_n`.

    Args:
        query: The (rewritten) user query.
        candidates: Stage 1 hybrid search results to re-rank.
        final_n: Number of top-scoring documents to keep. Defaults to
            `config.FINAL_N`.

    Returns:
        `candidates`, re-scored by the cross-encoder and sorted
        descending by relevance, truncated to `final_n`.
    """
    if not candidates:
        return []

    relevance_scores = score(query, [doc.search_text for doc in candidates])
    reranked = [
        replace(doc, score=relevance_score)
        for doc, relevance_score in zip(candidates, relevance_scores)
    ]
    reranked.sort(key=lambda doc: doc.score, reverse=True)
    return reranked[:final_n]
