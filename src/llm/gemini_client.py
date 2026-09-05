"""
Google Gemini LLM client implementation (spec.md section 6.2), targeting `gemini-2.5-flash`.
"""

from __future__ import annotations

import logging
import os
import threading
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel
from tenacity import before_sleep_log, retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.config import GEMINI_MODEL
from src.llm.base import LLMClient, LLMResponse

logger = logging.getLogger(__name__)

__all__ = ["GeminiClient"]


def _is_retryable_gemini_error(exc: BaseException) -> bool:
    """Retry on Gemini 5xx server errors and 429 rate limiting (`google.genai.errors`)."""
    if isinstance(exc, genai_errors.ServerError):
        return True
    return isinstance(exc, genai_errors.ClientError) and exc.code == 429


# Retries transient rate-limit/server errors so a single hiccup doesn't crash
# a `ThreadPoolExecutor` batch evaluation run (spec section 11.4).
_retry_gemini = retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(4),
    retry=retry_if_exception(_is_retryable_gemini_error),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)

# ---------------------------------------------------------------------------
# Process-wide rate limiter (bug fix, spec.md section 11.4 evaluation run).
#
# The Google Gemini free tier caps `gemini-2.5-flash` at 5 requests/minute
# PER PROJECT (i.e. shared across every concurrent caller, not per-client).
# `evaluate_llm.py` runs a `ThreadPoolExecutor` batch of up to 50 concurrent
# rows, and `src.llm.factory.get_llm()` constructs a brand-new `GeminiClient`
# instance per call -- so a per-instance throttle would do nothing; dozens of
# threads each fired their own request immediately, blowing through the quota
# in the first few seconds and exhausting `_retry_gemini`'s 4 attempts before
# the free-tier's own ~12s replenishment window could help.
#
# Fix: a single module-level lock + last-call timestamp, shared by every
# `GeminiClient` instance in this process, serializes real outbound Gemini
# requests to at most one every `_MIN_CALL_INTERVAL_SECONDS`. This trades
# wall-clock time (a full 50-row batch now takes minutes, not seconds) for
# actually respecting the account-wide quota instead of retry-storming it.
_gemini_rate_limit_lock = threading.Lock()
_gemini_last_call_monotonic: float = 0.0
# 5 requests/minute = 1 every 12s; pad slightly for clock/latency jitter.
_MIN_CALL_INTERVAL_SECONDS: float = 12.5


def _throttle_gemini_call() -> None:
    """Block the calling thread until it's safe to fire another Gemini request."""
    global _gemini_last_call_monotonic
    with _gemini_rate_limit_lock:
        now = time.monotonic()
        wait_seconds = _gemini_last_call_monotonic + _MIN_CALL_INTERVAL_SECONDS - now
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        _gemini_last_call_monotonic = time.monotonic()


class GeminiClient(LLMClient):
    """`LLMClient` implementation backed by the Google GenAI SDK."""

    def __init__(self, model: str = GEMINI_MODEL, api_key: str | None = None) -> None:
        self.model = model
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not resolved_key:
            logger.warning("No Gemini API key found (checked constructor arg, GEMINI_API_KEY, and GOOGLE_API_KEY env vars).")
        self._client = genai.Client(api_key=resolved_key)

    @staticmethod
    def _usage(response) -> tuple[int, int, int]:
        usage = getattr(response, "usage_metadata", None)
        prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
        completion_tokens = getattr(usage, "candidates_token_count", 0) or 0
        total_tokens = getattr(usage, "total_token_count", 0) or (prompt_tokens + completion_tokens)
        return prompt_tokens, completion_tokens, total_tokens

    @_retry_gemini
    def complete(self, prompt: str, system: str | None = None, **kwargs) -> LLMResponse:
        """Generate free-form text via `models.generate_content`."""
        config = types.GenerateContentConfig(system_instruction=system, **kwargs)

        _throttle_gemini_call()
        start = time.monotonic()
        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        latency = time.monotonic() - start

        prompt_tokens, completion_tokens, total_tokens = self._usage(response)
        return LLMResponse(
            text=response.text or "",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_seconds=latency,
            cost_usd=self._cost_usd(prompt_tokens, completion_tokens),
            model=self.model,
        )

    @_retry_gemini
    def structured(
        self, prompt: str, schema: type[BaseModel], system: str | None = None, **kwargs
    ) -> tuple[BaseModel, LLMResponse]:
        """Generate a response validated against `schema` via Gemini's JSON schema mode."""
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema.model_json_schema(),
            **kwargs,
        )

        _throttle_gemini_call()
        start = time.monotonic()
        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        latency = time.monotonic() - start

        prompt_tokens, completion_tokens, total_tokens = self._usage(response)
        raw_text = response.text or "{}"
        llm_response = LLMResponse(
            text=raw_text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_seconds=latency,
            cost_usd=self._cost_usd(prompt_tokens, completion_tokens),
            model=self.model,
        )
        try:
            parsed = schema.model_validate_json(raw_text)
        except Exception:
            logger.error("Failed to parse Gemini structured output as %s: %r", schema.__name__, raw_text)
            raise
        return parsed, llm_response
