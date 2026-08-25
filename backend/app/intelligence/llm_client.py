"""LLM client — provider-agnostic, with Gemini and a deterministic narrator.

The LLM's ONLY job is prose: it turns already-computed, structured facts into
natural language. It never computes numbers, rankings, evidence, confidence, or
risks (those are deterministic — see the recommendation engine and analytics).

Two backends behind one interface:

* **GeminiClient** — Gemini 3.6 Flash via ``google-genai``.
  Used when ``GEMINI_API_KEY`` is set and the SDK is installed. Retries with a
  timeout; on persistent failure it degrades to the narrator rather than raising.
* **DeterministicNarrator** — the default/fallback. Renders prose directly from
  the structured payload, so the pipeline is reproducible, cost-free, and
  offline-testable. Because the facts are the same, the output is grounded by
  construction.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from functools import partial
from time import monotonic
from typing import Protocol

from app.intelligence.explainability import GroundingResult, validate_grounded_narrative
from app.intelligence.generation import (
    GenerationBudget,
    GenerationMetadata,
    GenerationResult,
    TokenUsage,
    current_generation_budget,
    provider_metadata,
    use_generation_budget,
)
from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)
NarrativeValidator = Callable[[str], GroundingResult]


class LLMClient(Protocol):
    async def generate(
        self,
        system: str,
        prompt: str,
        fallback: str,
        validator: NarrativeValidator | None = None,
    ) -> GenerationResult | str:
        """Return prose and provenance for ``prompt`` (legacy strings accepted).

        ``fallback`` is deterministic text used if the model is unavailable or
        fails, so callers always receive grounded output.
        """
        ...


class DeterministicNarrator:
    """Returns the pre-rendered deterministic ``fallback`` text as the output.

    The prompt builder always supplies a fully-formed fallback narrative built
    from the structured facts, so this backend needs no model.
    """

    async def generate(
        self,
        system: str,
        prompt: str,
        fallback: str,
        validator: NarrativeValidator | None = None,
    ) -> GenerationResult:
        if validator:
            result = validator(fallback)
            if not result.valid:
                raise ValueError(f"Invalid deterministic narrative: {result.reason}")
        return GenerationResult(
            text=fallback,
            metadata=GenerationMetadata(
                configured_backend=type(self).__name__,
                backend="deterministic",
            ),
        )


class GeminiClient:
    """Gemini via google-genai. Lazy-loaded; degrades to fallback on error."""

    def __init__(self, api_key: str) -> None:
        from google import genai  # noqa: PLC0415 — optional dependency
        from google.genai import types  # noqa: PLC0415 — optional dependency

        self._timeout: float = settings.llm_timeout_seconds
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=self._timeout * 1000),
        )
        self._model = settings.llm_model
        self._retries = settings.llm_max_retries
        self._max_output_tokens = settings.llm_max_output_tokens
        self._thinking_budget = settings.llm_thinking_budget
        self._types = types

    async def generate(
        self,
        system: str,
        prompt: str,
        fallback: str,
        validator: NarrativeValidator | None = None,
    ) -> GenerationResult:
        started = monotonic()
        usage = TokenUsage()
        response_count = 0
        attempts = 0
        last_response = None
        for attempt in range(1, self._retries + 1):
            budget = current_generation_budget()
            remaining = (
                await budget.reserve_provider_call() if budget is not None else self._timeout
            )
            if remaining is None:
                logger.warning(
                    "gemini_request_budget_exhausted",
                    extra={
                        "attempts": attempts,
                        "provider_calls": budget.provider_calls if budget else 0,
                    },
                )
                break
            attempts = attempt
            attempt_timeout = min(self._timeout, remaining)
            try:
                async with asyncio.timeout(attempt_timeout):
                    resp = await self._client.aio.models.generate_content(
                        model=self._model,
                        contents=prompt,
                        config=self._types.GenerateContentConfig(
                            system_instruction=system,
                            candidate_count=1,
                            max_output_tokens=self._max_output_tokens,
                            thinking_config=self._types.ThinkingConfig(
                                thinking_budget=self._thinking_budget,
                                include_thoughts=False,
                            ),
                        ),
                    )
                last_response = resp
                response_count += 1
                usage = usage.add(TokenUsage.from_response(resp))
                finish_reason = _finish_reason(resp)
                if finish_reason and finish_reason != "STOP":
                    logger.warning(
                        "gemini_generate_rejected",
                        extra={
                            "attempt": attempt,
                            "reason": "incomplete_provider_response",
                            "finish_reason": finish_reason,
                        },
                    )
                    continue
                text = (getattr(resp, "text", None) or "").strip()
                if text:
                    result = validator(text) if validator else GroundingResult(True)
                    if result.valid:
                        return GenerationResult(
                            text=text,
                            metadata=provider_metadata(
                                resp,
                                configured_backend=type(self).__name__,
                                requested_model=self._model,
                                attempt_count=attempts,
                                provider_response_count=response_count,
                                latency_ms=_elapsed_ms(started),
                                usage=usage,
                            ),
                        )
                    logger.warning(
                        "gemini_generate_rejected",
                        extra={"attempt": attempt, "reason": _reason_code(result.reason)},
                    )
                else:
                    logger.warning("gemini_generate_empty", extra={"attempt": attempt})
            except TimeoutError:
                logger.warning(
                    "gemini_generate_timeout",
                    extra={"attempt": attempt, "timeout_seconds": attempt_timeout},
                )
            except Exception as exc:  # noqa: BLE001 — network/quota/etc.
                logger.warning(
                    "gemini_generate_failed",
                    extra={"attempt": attempt, "error": type(exc).__name__},
                )
        logger.warning("gemini_unavailable_using_fallback")
        metadata = (
            provider_metadata(
                last_response,
                configured_backend=type(self).__name__,
                requested_model=self._model,
                attempt_count=attempts,
                provider_response_count=response_count,
                latency_ms=_elapsed_ms(started),
                usage=usage,
            )
            if last_response is not None
            else GenerationMetadata(
                configured_backend=type(self).__name__,
                backend="gemini",
                requested_model=self._model,
                attempt_count=attempts,
                provider_response_count=response_count,
                latency_ms=_elapsed_ms(started),
                usage=usage,
            )
        )
        return GenerationResult(text=fallback, metadata=metadata.as_fallback())

    async def aclose(self) -> None:
        """Release the SDK's async and sync HTTP transports."""
        await self._client.aio.aclose()
        self._client.close()


async def generate_grounded(
    client: LLMClient, system: str, prompt: str, fallback: str
) -> str:
    """Generate prose with retry-time and post-generation grounding checks."""
    return (await generate_grounded_result(client, system, prompt, fallback)).text


async def generate_grounded_result(
    client: LLMClient,
    system: str,
    prompt: str,
    fallback: str,
    *,
    budget: GenerationBudget | None = None,
) -> GenerationResult:
    """Generate validated prose together with actual, sanitized provenance."""
    validator: NarrativeValidator = partial(validate_grounded_narrative, prompt=prompt)
    with use_generation_budget(budget):
        generated = await client.generate(system, prompt, fallback, validator)
    if isinstance(generated, GenerationResult):
        output = generated
    else:
        output = GenerationResult(
            text=generated,
            metadata=GenerationMetadata(
                configured_backend=type(client).__name__,
                backend="unknown",
            ),
        )
    result = validator(output.text)
    if result.valid:
        logger.info("llm_generation_completed", extra=output.metadata.log_fields())
        return output
    fallback_result = validator(fallback)
    if not fallback_result.valid:
        raise ValueError(f"Invalid deterministic narrative: {fallback_result.reason}")
    logger.warning(
        "llm_output_rejected_using_fallback",
        extra={"reason": _reason_code(result.reason)},
    )
    fallback_output = GenerationResult(
        text=fallback,
        metadata=output.metadata.as_fallback(),
    )
    logger.info("llm_generation_completed", extra=fallback_output.metadata.log_fields())
    return fallback_output


def _elapsed_ms(started: float) -> int:
    return max(0, round((monotonic() - started) * 1000))


def _reason_code(reason: str) -> str:
    """Keep validation categories while dropping provider-derived claim values."""
    return reason.partition(":")[0]


def _finish_reason(response: object) -> str | None:
    """Return the first candidate's normalized provider finish reason."""
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return None
    raw = getattr(candidates[0], "finish_reason", None)
    value = getattr(raw, "value", raw)
    if value is None:
        return None
    return str(value).rsplit(".", 1)[-1].upper()


_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Return a cached client: Gemini if configured+available, else the narrator."""
    global _client
    if _client is not None:
        return _client
    if settings.gemini_api_key:
        try:
            _client = GeminiClient(settings.gemini_api_key)
            logger.info("llm_backend_loaded", extra={"backend": "gemini"})
        except Exception as exc:  # noqa: BLE001 — SDK missing / bad config
            logger.warning(
                "gemini_unavailable_fallback_narrator",
                extra={"error": type(exc).__name__},
            )
            _client = DeterministicNarrator()
    else:
        _client = DeterministicNarrator()
    return _client


async def close_llm_client() -> None:
    """Close and clear the cached provider client during process shutdown."""
    global _client
    client, _client = _client, None
    if isinstance(client, GeminiClient):
        await client.aclose()
