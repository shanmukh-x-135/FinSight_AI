"""Tests for the LLM client abstraction (narrator default + Gemini fallback)."""

from __future__ import annotations

import pytest

from app.intelligence.llm_client import DeterministicNarrator, get_llm_client


def test_narrator_returns_fallback() -> None:
    assert DeterministicNarrator().generate("sys", "prompt", "the fallback") == "the fallback"


def test_default_backend_is_narrator() -> None:
    assert isinstance(get_llm_client(), DeterministicNarrator)


def test_gemini_client_success_and_failure_paths(monkeypatch) -> None:
    pytest.importorskip("google.genai")
    from app.intelligence.llm_client import GeminiClient

    client = GeminiClient("dummy-key")

    class _Resp:
        text = "gemini prose"

    # Success → returns model text.
    client._client.models.generate_content = lambda **_k: _Resp()
    assert client.generate("sys", "prompt", "fb") == "gemini prose"

    # Empty text → falls back.
    class _Empty:
        text = ""

    client._client.models.generate_content = lambda **_k: _Empty()
    assert client.generate("sys", "prompt", "fb") == "fb"

    # Exception (network/quota) → retries then falls back, never raises.
    def _boom(**_k):
        raise RuntimeError("api down")

    client._client.models.generate_content = _boom
    assert client.generate("sys", "prompt", "fb") == "fb"
