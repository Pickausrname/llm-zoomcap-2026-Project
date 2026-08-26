"""
Provider-agnostic LLM abstraction (spec.md section 6).

Every LLM call in this application -- query rewriting (Stage 0), RAG
generation, the relevance judge, ground-truth generation, and the A/B
model-swap evaluation -- goes through this interface, never a specific
vendor SDK directly. `factory.get_llm()` is the single swap point.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic import BaseModel

from src.config import PRICING_PER_1K_TOKENS

__all__ = ["LLMResponse", "LLMClient"]


@dataclass
class LLMResponse:
    """Bundles an LLM completion's text together with usage/cost/latency metrics."""

    text: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_seconds: float
    cost_usd: float
    model: str


class LLMClient(ABC):
    """Provider-agnostic interface implemented by each concrete LLM client."""

    # Every concrete client must set this in __init__ (the model id used for
    # both generation calls and `_cost_usd`'s `PRICING_PER_1K_TOKENS` lookup).
    model: str

    def _cost_usd(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Compute USD cost from `config.PRICING_PER_1K_TOKENS` for `self.model`."""
        pricing = PRICING_PER_1K_TOKENS.get(self.model, {"prompt": 0.0, "completion": 0.0})
        return (prompt_tokens / 1000) * pricing["prompt"] + (completion_tokens / 1000) * pricing["completion"]

    @abstractmethod
    def complete(self, prompt: str, system: str | None = None, **kwargs) -> LLMResponse:
        """Generate free-form text for `prompt` (optionally under a `system` instruction)."""
        raise NotImplementedError

    @abstractmethod
    def structured(
        self, prompt: str, schema: type[BaseModel], system: str | None = None, **kwargs
    ) -> tuple[BaseModel, LLMResponse]:
        """
        Generate a response validated against `schema`.

        Returns:
            A tuple of `(parsed_model_instance, response_metadata)`, where
            `response_metadata.text` holds the raw JSON text returned by
            the model.
        """
        raise NotImplementedError
