"""P10.7 generation provenance aggregation and disclosure safety."""

from __future__ import annotations

from app.intelligence.generation import (
    GenerationMetadata,
    TokenUsage,
    backend_label,
    generation_record,
    summarize_generations,
)


def test_mixed_generation_summary_tracks_actual_usage_and_fallbacks() -> None:
    accepted = GenerationMetadata(
        configured_backend="GeminiClient",
        backend="gemini",
        requested_model="gemini-3.6-flash",
        model_version="gemini-3.6-flash-001",
        response_id="safe-response-id",
        finish_reason="STOP",
        attempt_count=1,
        provider_response_count=1,
        latency_ms=20,
        usage=TokenUsage(prompt_tokens=10, candidate_tokens=4, total_tokens=14),
    )
    fallback = GenerationMetadata(
        configured_backend="GeminiClient",
        backend="deterministic",
        requested_model="gemini-3.6-flash",
        attempt_count=2,
        provider_response_count=1,
        fallback_used=True,
        latency_ms=30,
        usage=TokenUsage(prompt_tokens=8, candidate_tokens=2, total_tokens=10),
    )
    summary = summarize_generations(
        [
            generation_record("market_summary", accepted),
            generation_record("executive_summary", fallback),
        ],
        configured_backend="GeminiClient",
    )

    assert summary["actual_backends"] == ["deterministic", "gemini"]
    assert summary["requested_models"] == ["gemini-3.6-flash"]
    assert summary["model_versions"] == ["gemini-3.6-flash-001"]
    assert summary["generation_count"] == 2
    assert summary["provider_attempt_count"] == 3
    assert summary["provider_response_count"] == 2
    assert summary["fallback_count"] == 1
    assert summary["usage"] == {
        "prompt_tokens": 18,
        "candidate_tokens": 6,
        "total_tokens": 24,
        "cached_tokens": None,
        "thoughts_tokens": None,
    }
    assert backend_label(summary) == "Gemini + deterministic fallback"


def test_persisted_metadata_excludes_prompts_responses_errors_and_credentials() -> None:
    metadata = GenerationMetadata(
        configured_backend="GeminiClient",
        backend="gemini",
        requested_model="gemini-3.6-flash",
        response_id="provider-id",
        attempt_count=1,
        provider_response_count=1,
    ).to_dict()
    serialized_keys = set(metadata) | set(metadata["usage"])

    assert not {
        "api_key",
        "prompt",
        "system_instruction",
        "response_text",
        "error_message",
    }.intersection(serialized_keys)


def test_optional_usage_addition_preserves_unknown_values() -> None:
    first = TokenUsage(prompt_tokens=10, total_tokens=10)
    second = TokenUsage(candidate_tokens=3, total_tokens=3)

    assert first.add(second) == TokenUsage(
        prompt_tokens=10,
        candidate_tokens=3,
        total_tokens=13,
    )
