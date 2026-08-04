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

from typing import Protocol

from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)


class LLMClient(Protocol):
    def generate(self, system: str, prompt: str, fallback: str) -> str:
        """Return prose for ``prompt``. ``fallback`` is deterministic text used
        if the model is unavailable/fails, so callers always get valid output."""
        ...


class DeterministicNarrator:
    """Returns the pre-rendered deterministic ``fallback`` text as the output.

    The prompt builder always supplies a fully-formed fallback narrative built
    from the structured facts, so this backend needs no model.
    """

    def generate(self, system: str, prompt: str, fallback: str) -> str:
        return fallback


class GeminiClient:
    """Gemini Flash via google-genai. Lazy-loaded; degrades to fallback on error."""

    def __init__(self, api_key: str) -> None:
        from google import genai  # noqa: PLC0415 — optional dependency

        self._client = genai.Client(api_key=api_key)
        self._model = settings.llm_model
        self._retries = settings.llm_max_retries

    def generate(self, system: str, prompt: str, fallback: str) -> str:
        contents = f"{system}\n\n{prompt}"
        for attempt in range(1, self._retries + 1):
            try:
                resp = self._client.models.generate_content(
                    model=self._model, contents=contents
                )
                text = (getattr(resp, "text", None) or "").strip()
                if text:
                    return text
            except Exception as exc:  # noqa: BLE001 — network/quota/etc.
                logger.warning(
                    "gemini_generate_failed",
                    extra={"attempt": attempt, "error": type(exc).__name__},
                )
        logger.warning("gemini_unavailable_using_fallback")
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
