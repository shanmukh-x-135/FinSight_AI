"""Provider-neutral generation results and safe production provenance."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from time import monotonic
from typing import Any


@dataclass
class GenerationBudget:
    """One shared latency and provider-call budget for an application request."""

    total_seconds: float
    max_provider_calls: int
    started_at: float = 0.0

    def __post_init__(self) -> None:
        if self.total_seconds <= 0:
            raise ValueError("total_seconds must be positive")
        if self.max_provider_calls < 1:
            raise ValueError("max_provider_calls must be positive")
        if self.started_at == 0.0:
            self.started_at = monotonic()
        self._provider_calls = 0
        self._lock = asyncio.Lock()

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.total_seconds - (monotonic() - self.started_at))

    @property
    def provider_calls(self) -> int:
        return self._provider_calls

    async def reserve_provider_call(self) -> float | None:
        """Reserve one real provider attempt and return its remaining deadline."""
        async with self._lock:
            remaining = self.remaining_seconds
            if remaining <= 0 or self._provider_calls >= self.max_provider_calls:
                return None
            self._provider_calls += 1
            return remaining


_generation_budget: ContextVar[GenerationBudget | None] = ContextVar(
    "generation_budget", default=None
)


@contextmanager
def use_generation_budget(budget: GenerationBudget | None):
    token = _generation_budget.set(budget)
    try:
        yield
    finally:
        _generation_budget.reset(token)


def current_generation_budget() -> GenerationBudget | None:
    return _generation_budget.get()


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int | None = None
    candidate_tokens: int | None = None
    total_tokens: int | None = None
    cached_tokens: int | None = None
    thoughts_tokens: int | None = None

    @classmethod
    def from_response(cls, response: Any) -> "TokenUsage":
        usage = getattr(response, "usage_metadata", None)
        return cls(
            prompt_tokens=_count(usage, "prompt_token_count"),
            candidate_tokens=_count(usage, "candidates_token_count"),
            total_tokens=_count(usage, "total_token_count"),
            cached_tokens=_count(usage, "cached_content_token_count"),
            thoughts_tokens=_count(usage, "thoughts_token_count"),
        )

    def add(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            **{
                field: _add_optional(getattr(self, field), getattr(other, field))
                for field in self.__dataclass_fields__
            }
        )

    def to_dict(self) -> dict[str, int | None]:
        return asdict(self)


@dataclass(frozen=True)
class GenerationMetadata:
    configured_backend: str
    backend: str
    requested_model: str | None = None
    model_version: str | None = None
    response_id: str | None = None
    finish_reason: str | None = None
    provider_created_at: str | None = None
    attempt_count: int = 0
    provider_response_count: int = 0
    fallback_used: bool = False
    latency_ms: int = 0
    usage: TokenUsage = TokenUsage()

    def as_fallback(self) -> "GenerationMetadata":
        return replace(self, backend="deterministic", fallback_used=True)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["usage"] = self.usage.to_dict()
        return data

    def log_fields(self) -> dict[str, Any]:
        """Bounded fields safe for logs; never includes prompts or provider text."""
        return {
            "configured_backend": self.configured_backend,
            "backend": self.backend,
            "requested_model": self.requested_model,
            "model_version": self.model_version,
            "attempt_count": self.attempt_count,
            "provider_response_count": self.provider_response_count,
            "fallback_used": self.fallback_used,
            "latency_ms": self.latency_ms,
            **self.usage.to_dict(),
        }


@dataclass(frozen=True)
class GenerationResult:
    text: str
    metadata: GenerationMetadata


def provider_metadata(
    response: Any,
    *,
    configured_backend: str,
    requested_model: str,
    attempt_count: int,
    provider_response_count: int,
    latency_ms: int,
    usage: TokenUsage,
) -> GenerationMetadata:
    candidates = getattr(response, "candidates", None) or []
    finish_reason = (
        _enum_text(getattr(candidates[0], "finish_reason", None)) if candidates else None
    )
    created_at = getattr(response, "create_time", None)
    return GenerationMetadata(
        configured_backend=configured_backend,
        backend="gemini",
        requested_model=requested_model,
        model_version=_text(getattr(response, "model_version", None)),
        response_id=_text(getattr(response, "response_id", None)),
        finish_reason=finish_reason,
        provider_created_at=(
            created_at.isoformat() if isinstance(created_at, datetime) else None
        ),
        attempt_count=attempt_count,
        provider_response_count=provider_response_count,
        latency_ms=latency_ms,
        usage=usage,
    )


def generation_record(purpose: str, metadata: GenerationMetadata) -> dict[str, Any]:
    return {"purpose": purpose, **metadata.to_dict()}


def summarize_generations(
    records: list[dict[str, Any]], *, configured_backend: str
) -> dict[str, Any]:
    usage_fields = TokenUsage.__dataclass_fields__.keys()
    actual_backends = sorted({str(item["backend"]) for item in records})
    requested_models = sorted(
        {str(item["requested_model"]) for item in records if item["requested_model"]}
    )
    model_versions = sorted(
        {str(item["model_version"]) for item in records if item["model_version"]}
    )
    usage = {
        field: _sum_present([item.get("usage", {}).get(field) for item in records])
        for field in usage_fields
    }
    return {
        "schema_version": 1,
        "configured_backend": configured_backend,
        "actual_backends": actual_backends,
        "requested_models": requested_models,
        "model_versions": model_versions,
        "generation_count": len(records),
        "provider_attempt_count": sum(int(item["attempt_count"]) for item in records),
        "provider_response_count": sum(
            int(item["provider_response_count"]) for item in records
        ),
        "fallback_count": sum(bool(item["fallback_used"]) for item in records),
        "usage": usage,
        "items": records,
    }


def backend_label(summary: dict[str, Any]) -> str:
    actual = set(summary["actual_backends"])
    if actual == {"deterministic"}:
        return "DeterministicNarrator"
    if actual == {"gemini"}:
        return "Gemini"
    if actual == {"deterministic", "gemini"}:
        return "Gemini + deterministic fallback"
    return " + ".join(sorted(actual)) or str(summary["configured_backend"])


def _count(value: Any, attribute: str) -> int | None:
    raw = getattr(value, attribute, None) if value is not None else None
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        return None
    return raw


def _add_optional(left: int | None, right: int | None) -> int | None:
    values = [value for value in (left, right) if value is not None]
    return sum(values) if values else None


def _sum_present(values: list[Any]) -> int | None:
    counts = [
        value
        for value in values
        if isinstance(value, int) and not isinstance(value, bool)
    ]
    return sum(counts) if counts else None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _enum_text(value: Any) -> str | None:
    return _text(getattr(value, "value", value))
