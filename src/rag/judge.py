"""
Built-in LLM relevance judge (spec.md section 10.2).

Immediately after `generator.generate_answer()` produces a
`conversation_id`, this module asks an LLM to grade the relevance of
the system's own answer to the original query, via structured output
(`src.llm.factory.get_llm(...).structured()`), and persists the
verdict to the `feedback` table as `source="judge"`
(`src.db.monitoring_store.insert_feedback`, spec.md section 12.2).

Deliberately takes only `(user_query, answer)` -- not the retrieved
context documents. `generator.generate_answer()` doesn't return its
retrieved `Document`s today, and widening `GeneratedAnswer`'s contract
just to let the judge second-guess groundedness would be a bigger
change than spec section 10.2 asks for ("evaluates the relevance of
the system's own answer" to the query, not a faithfulness-to-context
check). Revisit only if a future spec requirement explicitly needs
context-aware judging.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from src.db.monitoring_store import insert_feedback
from src.llm.factory import get_llm

logger = logging.getLogger(__name__)

__all__ = ["RelevanceVerdict", "JudgeResult", "judge_answer"]

_SYSTEM_PROMPT = (
    "You are a strict relevance judge for a MOSFET selection RAG system. "
    "Given the user's original query and the system's generated answer, "
    "judge ONLY how relevant the answer is to the query -- not whether it "
    "is grounded in any particular datasheet.\n\n"
    "Respond with:\n"
    "- RELEVANT: the answer directly addresses the query.\n"
    "- PARTLY_RELEVANT: the answer addresses part of the query, or is "
    "vague/incomplete relative to it.\n"
    "- NON_RELEVANT: the answer does not address the query at all.\n\n"
    "Always include a brief explanation of your reasoning."
)

# Judgment call (spec section 10.2 leaves the label->score mapping undefined):
# a signed scale mirroring the user +1/-1 feedback convention (spec section
# 12.2), with PARTLY_RELEVANT at the neutral midpoint. Not spec-mandated --
# see /memories/repo/project-notes.md.
_LABEL_TO_SCORE: dict[str, int] = {
    "RELEVANT": 1,
    "PARTLY_RELEVANT": 0,
    "NON_RELEVANT": -1,
}


class RelevanceVerdict(BaseModel):
    """Structured-output schema for the judge LLM call (spec.md section 10.2)."""

    label: Literal["RELEVANT", "PARTLY_RELEVANT", "NON_RELEVANT"]
    explanation: str


@dataclass
class JudgeResult:
    """The judge's verdict plus the id of the `feedback` row it was persisted to."""

    label: str
    explanation: str
    score: int
    feedback_id: int


def _build_prompt(user_query: str, answer: str) -> str:
    """Build the user-turn prompt (query + answer) sent to the judge LLM."""
    return f"Query: {user_query}\n\nAnswer: {answer}"


def judge_answer(
    user_query: str,
    answer: str,
    conversation_id: str,
    provider: str | None = None,
) -> JudgeResult:
    """
    Judge the relevance of `answer` to `user_query` and persist the verdict.

    Creates a fresh `LLMClient` for this call only (`src.llm.factory.get_llm`
    holds no shared state), so this function is safe to call concurrently
    from multiple threads (e.g. `evaluate_llm.py`'s `ThreadPoolExecutor`
    batch, spec.md section 11.4).

    Args:
        user_query: The original natural-language query.
        answer: The system's generated answer (`GeneratedAnswer.answer`).
        conversation_id: The `conversations.id` this verdict is linked to
            (`GeneratedAnswer.conversation_id` from `generate_answer()`).
        provider: Optional LLM provider override (`"openai"`/`"gemini"`),
            forwarded to `src.llm.factory.get_llm`. Defaults to
            `config.DEFAULT_LLM_PROVIDER` when omitted.

    Returns:
        A `JudgeResult` with the verdict's label, explanation, mapped
        numeric score, and the persisted `feedback` row id.

    Raises:
        Exception: Re-raises whatever `get_llm(...).structured()` OR
            `insert_feedback(...)` raises (unknown provider, missing
            credentials, rate limits, parse failures, FK/constraint
            violations, etc.) instead of `generator.generate_answer()`'s
            fallback-and-persist pattern. A fabricated relevance verdict
            would corrupt real monitoring data, which is worse than a
            missing feedback row -- and under `evaluate_llm.py`'s
            `ThreadPoolExecutor` batch (spec.md section 11.4), letting
            the exception propagate through the submitted future is the
            normal way for the caller to detect and count/skip that one
            failed item without losing visibility into the failure or
            silently under-reporting judge coverage. Both failure points
            are logged (`logger.error(..., exc_info=True)`) before the
            re-raise.
    """
    prompt = _build_prompt(user_query, answer)
    try:
        llm = get_llm(provider)
        verdict, _response = llm.structured(prompt, RelevanceVerdict, system=_SYSTEM_PROMPT)
    except Exception:
        logger.error(
            "Judge LLM call failed for conversation %s (provider=%r)",
            conversation_id,
            provider,
            exc_info=True,
        )
        raise

    score = _LABEL_TO_SCORE[verdict.label]
    try:
        feedback_id = insert_feedback(
            conversation_id=conversation_id,
            source="judge",
            score=score,
            label=verdict.label,
            explanation=verdict.explanation,
        )
    except Exception:
        # Verdict was produced (LLM call already succeeded/cost incurred) but persistence
        # failed -- log the verdict itself so it isn't silently lost, then re-raise.
        logger.error(
            "Failed to persist judge feedback for conversation %s (label=%s, score=%d, "
            "explanation=%r)",
            conversation_id,
            verdict.label,
            score,
            verdict.explanation,
            exc_info=True,
        )
        raise

    logger.info(
        "Judge feedback %s persisted for conversation %s (label=%s, score=%d)",
        feedback_id,
        conversation_id,
        verdict.label,
        score,
    )

    return JudgeResult(
        label=verdict.label,
        explanation=verdict.explanation,
        score=score,
        feedback_id=feedback_id,
    )
