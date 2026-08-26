"""
Stage 0 -- Query rewriting (spec.md section 9.1).

Expands the user's raw natural-language query (acronyms, technical
constraints such as "RoHS", "fast-switching") into an optimized search
query string via the LLM abstraction (`src.llm.factory.get_llm`), before
handing it to Stage 1 hybrid search.
"""

from __future__ import annotations

import logging

from src.llm.factory import get_llm

logger = logging.getLogger(__name__)

__all__ = ["rewrite_query"]

_SYSTEM_PROMPT = (
    "You are a query optimization assistant for a MOSFET datasheet search "
    "engine. Rewrite the user's natural-language request into a concise, "
    "keyword-rich search query for a hybrid lexical + vector search index "
    "over electronic component datasheets.\n\n"
    "Expand any acronyms, standards, and informal technical phrases into "
    "the precise terminology datasheets use (for example: \"RoHS\" -> "
    "\"RoHS compliant, lead-free\"; \"fast-switching\" -> \"low gate charge, "
    "low switching losses, high frequency switching\"). Preserve every "
    "explicit constraint from the original request (voltage/current "
    "ratings, package type, manufacturer, etc.).\n\n"
    "Respond with ONLY the rewritten search query text -- no preamble, "
    "no explanation, no quotes."
)


def rewrite_query(user_query: str, provider: str | None = None) -> str:
    """
    Expand `user_query` into an optimized search query via the LLM abstraction.

    Creates a fresh `LLMClient` for this call only (`src.llm.factory.get_llm`
    holds no shared state), so this function is safe to call concurrently
    from multiple threads (spec.md section 11.4).

    Args:
        user_query: The raw natural-language query as typed by the user.
        provider: Optional LLM provider override (`"openai"`/`"gemini"`),
            forwarded to `src.llm.factory.get_llm`. Defaults to
            `config.DEFAULT_LLM_PROVIDER` when omitted.

    Returns:
        The rewritten search query string. Falls back to `user_query`
        unchanged if the LLM returns an empty response, or if the LLM call
        itself fails (network/timeout/provider outage) -- Stage 0 must
        never take down the rest of the retrieval pipeline.
    """
    try:
        llm = get_llm(provider)
        response = llm.complete(user_query, system=_SYSTEM_PROMPT)
        rewritten = response.text.strip()
    except Exception:
        logger.warning("Query rewrite LLM call failed; falling back to raw query.", exc_info=True)
        return user_query
    if not rewritten:
        logger.warning("Query rewrite returned empty text; falling back to raw query.")
        return user_query
    return rewritten
