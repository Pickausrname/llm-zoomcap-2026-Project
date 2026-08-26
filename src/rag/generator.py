"""
RAG answer generation (spec.md section 10.1).

Orchestrates the full query-to-answer flow: Stage 0-2 retrieval
(`src.retrieval.pipeline.retrieve`) -> grounded prompt construction ->
LLM generation (`src.llm.factory.get_llm`) -> monitoring capture
(`src.db.monitoring_store.insert_conversation`, spec.md section 12.1).

Holds no module-level mutable state; every function it calls
(`retrieve`, `get_llm`, `insert_conversation`) is itself safe under
concurrent `ThreadPoolExecutor` use (spec.md section 11.4).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.db.monitoring_store import insert_conversation
from src.llm.base import LLMResponse
from src.llm.factory import get_llm
from src.retrieval.hybrid_search import Document
from src.retrieval.pipeline import retrieve

logger = logging.getLogger(__name__)

__all__ = ["GeneratedAnswer", "generate_answer"]

_SYSTEM_PROMPT = (
    "You are a MOSFET selection assistant. Answer ONLY using the "
    "datasheet context provided below -- never rely on outside "
    "knowledge. Cite the `part_number` of the datasheet backing every "
    "claim you make (for example: \"the IRFZ44N has a maximum Vds of "
    "55V [IRFZ44N]\").\n\n"
    "If the context does not contain enough information to answer the "
    "question, say plainly that you don't know -- never guess or "
    "fabricate a part number, specification, or claim."
)

_NO_CONTEXT_MESSAGE = "No matching MOSFET datasheet content was retrieved for this query."

# Returned (and still logged to monitoring) when the LLM call fails outright, so a
# provider outage never crashes generate_answer() nor loses telemetry visibility into it.
_GENERATION_FAILURE_MESSAGE = (
    "I'm sorry, the generation service is currently unavailable. Please try again later."
)
_GENERATION_FAILURE_MODEL = "generation-failed"


@dataclass
class GeneratedAnswer:
    """The grounded answer plus every execution metric needed for monitoring capture."""

    conversation_id: str
    answer: str
    prompt: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_seconds: float
    cost_usd: float


def _format_context(documents: list[Document]) -> str:
    """Render retrieved documents into citable context blocks, or a no-context notice."""
    if not documents:
        return _NO_CONTEXT_MESSAGE
    blocks = [
        f"[part_number: {doc.part_number}] "
        f"(component_type: {doc.component_type}, manufacturer: {doc.manufacturer_name})\n"
        f"{doc.search_text}"
        for doc in documents
    ]
    return "\n\n".join(blocks)


def _build_user_prompt(user_query: str, documents: list[Document]) -> str:
    """Build the user-turn prompt (context + question) sent to the LLM alongside `_SYSTEM_PROMPT`."""
    context = _format_context(documents)
    return f"Context:\n{context}\n\nQuestion: {user_query}"


def generate_answer(user_query: str, provider: str | None = None) -> GeneratedAnswer:
    """
    Generate a grounded answer for `user_query` and persist it to the monitoring store.

    Runs the full retrieval pipeline, builds a prompt instructing the
    LLM to answer only from the retrieved datasheet context and cite
    `part_number`s, generates the answer, and logs the conversation
    (spec.md section 12.1) so `rag/judge.py` and the Streamlit
    `qa_panel.py` can attach `feedback` rows via the returned
    `conversation_id`.

    Args:
        user_query: The raw natural-language query as typed by the user.
        provider: Optional LLM provider override (`"openai"`/`"gemini"`),
            forwarded to `src.llm.factory.get_llm`. Defaults to
            `config.DEFAULT_LLM_PROVIDER` when omitted.

    Returns:
        A `GeneratedAnswer` with the answer text, full prompt, the
        persisted `conversation_id`, and all usage/cost/latency metrics.

        Never raises for LLM-side failures (unknown `provider`, missing
        credentials, rate limits, timeouts, outages, etc.) -- falls back
        to `_GENERATION_FAILURE_MESSAGE`/`_GENERATION_FAILURE_MODEL` and
        still persists the conversation, so the failure is visible in
        monitoring instead of crashing the request. Retrieval-layer
        failures (`retrieve()`) are intentionally NOT caught here and
        propagate, since those indicate an infrastructure-level outage
        (DB/ONNX runtime down) rather than a transient LLM hiccup.
    """
    result = retrieve(user_query)
    logger.info(
        "Retrieved %d documents for generation (rewritten query: %r)",
        len(result.documents),
        result.rewritten_query,
    )

    prompt = _build_user_prompt(user_query, result.documents)

    try:
        llm = get_llm(provider)
        response = llm.complete(prompt, system=_SYSTEM_PROMPT)
    except Exception:
        logger.error(
            "LLM generation failed for query %r (provider=%r)", user_query, provider, exc_info=True
        )
        response = LLMResponse(
            text=_GENERATION_FAILURE_MESSAGE,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            latency_seconds=0.0,
            cost_usd=0.0,
            model=_GENERATION_FAILURE_MODEL,
        )

    # Full record of what was actually sent to the LLM (system + user turn), stored for monitoring.
    full_prompt = f"{_SYSTEM_PROMPT}\n\n{prompt}"

    conversation_id = insert_conversation(
        query=user_query,
        rewritten_query=result.rewritten_query,
        answer=response.text,
        prompt=full_prompt,
        model=response.model,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        total_tokens=response.total_tokens,
        response_time=response.latency_seconds,
        cost=response.cost_usd,
    )
    logger.info("Conversation %s persisted to monitoring store", conversation_id)

    return GeneratedAnswer(
        conversation_id=conversation_id,
        answer=response.text,
        prompt=full_prompt,
        model=response.model,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        total_tokens=response.total_tokens,
        latency_seconds=response.latency_seconds,
        cost_usd=response.cost_usd,
    )
