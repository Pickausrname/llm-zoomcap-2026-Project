"""
Single swap point for choosing an `LLMClient` implementation (spec.md section 6.3).
"""

from __future__ import annotations

from src.config import DEFAULT_LLM_PROVIDER
from src.llm.base import LLMClient
from src.llm.gemini_client import GeminiClient
from src.llm.openai_client import OpenAIClient

__all__ = ["get_llm"]

_PROVIDERS: dict[str, type[LLMClient]] = {
    "openai": OpenAIClient,
    "gemini": GeminiClient,
}


def get_llm(provider: str | None = None) -> LLMClient:
    """
    Return an `LLMClient` for `provider`, defaulting to `config.DEFAULT_LLM_PROVIDER`.

    Args:
        provider: `"openai"` or `"gemini"`. Falls back to
            `config.DEFAULT_LLM_PROVIDER` when omitted.

    Raises:
        ValueError: If `provider` is not one of the supported providers.
    """
    resolved = (provider or DEFAULT_LLM_PROVIDER).lower()
    try:
        client_cls = _PROVIDERS[resolved]
    except KeyError:
        raise ValueError(
            f"Unsupported LLM provider {resolved!r}. Supported providers: {sorted(_PROVIDERS)}."
        ) from None
    return client_cls()
