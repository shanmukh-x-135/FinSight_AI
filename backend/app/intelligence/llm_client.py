"""LLM client — provider-agnostic, with Gemini and a deterministic narrator.

The LLM's ONLY job is prose: it turns already-computed, structured facts into
natural language. It never computes numbers, rankings, evidence, confidence, or
risks (those are deterministic — see the recommendation engine and analytics).

Two backends behind one interface:

* **GeminiClient** — Gemini Flash via ``google-genai`` (design doc's model).
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
from typing import Protocol

from app.intelligence.explainability import GroundingResult, validate_grounded_narrative
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
    ) -> str:
        """Return prose for ``prompt``. ``fallback`` is deterministic text used
        if the model is unavailable/fails, so callers always get valid output."""
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
    ) -> str:
        if validator:
            result = validator(fallback)
            if not result.valid:
                raise ValueError(f"Invalid deterministic narrative: {result.reason}")
        return fallback


class GeminiClient:
    """Gemini Flash via google-genai. Lazy-loaded; degrades to fallback on error."""

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

    async def generate(
        self,
        system: str,
        prompt: str,
        fallback: str,
        validator: NarrativeValidator | None = None,
    ) -> str:
        contents = f"{system}\n\n{prompt}"
        for attempt in range(1, self._retries + 1):
            try:
                async with asyncio.timeout(self._timeout):
                    resp = await self._client.aio.models.generate_content(
                        model=self._model, contents=contents
                    )
                text = (getattr(resp, "text", None) or "").strip()
                if text:
                    result = validator(text) if validator else GroundingResult(True)
                    if result.valid:
                        return text
                    logger.warning(
                        "gemini_generate_rejected",
                        extra={"attempt": attempt, "reason": result.reason},
                    )
            except TimeoutError:
                logger.warning(
                    "gemini_generate_timeout",
                    extra={"attempt": attempt, "timeout_seconds": self._timeout},
                )
            except Exception as exc:  # noqa: BLE001 — network/quota/etc.
                logger.warning(
                    "gemini_generate_failed",
                    extra={"attempt": attempt, "error": type(exc).__name__},
                )
        logger.warning("gemini_unavailable_using_fallback")
        return fallback


async def generate_grounded(
    client: LLMClient, system: str, prompt: str, fallback: str
) -> str:
    """Generate prose with retry-time and post-generation grounding checks."""
    validator: NarrativeValidator = partial(validate_grounded_narrative, prompt=prompt)
    narrative = await client.generate(system, prompt, fallback, validator)
    result = validator(narrative)
    if result.valid:
        return narrative
    fallback_result = validator(fallback)
    if not fallback_result.valid:
        raise ValueError(f"Invalid deterministic narrative: {fallback_result.reason}")
    logger.warning("llm_output_rejected_using_fallback", extra={"reason": result.reason})
    return fallback


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
