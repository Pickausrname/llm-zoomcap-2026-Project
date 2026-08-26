"""
OpenAI LLM client implementation (spec.md section 6.2), targeting `gpt-5.4-mini`.
"""

from __future__ import annotations

import logging
import os
import time

import openai
from openai import OpenAI
from pydantic import BaseModel
from tenacity import before_sleep_log, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import OPENAI_MODEL
from src.llm.base import LLMClient, LLMResponse

logger = logging.getLogger(__name__)

__all__ = ["OpenAIClient"]

# Retries transient rate-limit/connection/server errors so a single hiccup
# doesn't crash a `ThreadPoolExecutor` batch evaluation run (spec section 11.4).
_retry_openai = retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(4),
    retry=retry_if_exception_type((openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


def _strip_markdown_fence(text: str) -> str:
    """Strip a ```-fenced code block wrapper, if the model added one despite JSON mode."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        if len(lines) >= 2 and lines[-1].strip() == "```":
            stripped = "\n".join(lines[1:-1]).strip()
    return stripped


class OpenAIClient(LLMClient):
    """`LLMClient` implementation backed by the OpenAI Chat Completions API."""

    def __init__(self, model: str = OPENAI_MODEL, api_key: str | None = None) -> None:
        self.model = model
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not resolved_key:
            logger.warning("No OpenAI API key found (checked constructor arg and OPENAI_API_KEY env var).")
        self._client = OpenAI(api_key=resolved_key)

    @staticmethod
    def _messages(prompt: str, system: str | None) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    @_retry_openai
    def complete(self, prompt: str, system: str | None = None, **kwargs) -> LLMResponse:
        """Generate free-form text via the Chat Completions API."""
        start = time.monotonic()
        completion = self._client.chat.completions.create(
            model=self.model,
            messages=self._messages(prompt, system),
            **kwargs,
        )
        latency = time.monotonic() - start

        usage = completion.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else prompt_tokens + completion_tokens

        return LLMResponse(
            text=completion.choices[0].message.content or "",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_seconds=latency,
            cost_usd=self._cost_usd(prompt_tokens, completion_tokens),
            model=self.model,
        )

    @_retry_openai
    def structured(
        self, prompt: str, schema: type[BaseModel], system: str | None = None, **kwargs
    ) -> tuple[BaseModel, LLMResponse]:
        """
        Generate a response validated against `schema`.

        Uses Chat Completions JSON mode plus the schema's own JSON Schema
        embedded in the prompt, rather than a provider/SDK-version-specific
        strict-schema response format, so this works across any Chat
        Completions-compatible model.
        """
        schema_instruction = (
            "Respond with a single JSON object that strictly matches this JSON Schema. "
            "Do not include any text outside the JSON object.\n\n"
            f"{schema.model_json_schema()}"
        )
        full_system = f"{system}\n\n{schema_instruction}" if system else schema_instruction

        start = time.monotonic()
        completion = self._client.chat.completions.create(
            model=self.model,
            messages=self._messages(prompt, full_system),
            response_format={"type": "json_object"},
            **kwargs,
        )
        latency = time.monotonic() - start

        usage = completion.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else prompt_tokens + completion_tokens
        raw_text = completion.choices[0].message.content or "{}"

        response = LLMResponse(
            text=raw_text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_seconds=latency,
            cost_usd=self._cost_usd(prompt_tokens, completion_tokens),
            model=self.model,
        )
        try:
            parsed = schema.model_validate_json(_strip_markdown_fence(raw_text))
        except Exception:
            logger.error("Failed to parse OpenAI structured output as %s: %r", schema.__name__, raw_text)
            raise
        return parsed, response
