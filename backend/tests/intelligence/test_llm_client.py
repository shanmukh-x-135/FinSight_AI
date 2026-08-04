"""Tests for the LLM client abstraction (narrator default + Gemini fallback)."""

from __future__ import annotations

import asyncio

import pytest

from app.intelligence import prompt_builder as pb
from app.intelligence.llm_client import (
    DeterministicNarrator,
    generate_grounded,
    get_llm_client,
)
from app.intelligence.recommendation_engine import Recommendation
from config.settings import settings


@pytest.mark.asyncio
async def test_narrator_returns_fallback() -> None:
    assert (
        await DeterministicNarrator().generate("sys", "prompt", "the fallback")
        == "the fallback"
    )


def test_default_backend_is_narrator() -> None:
    assert isinstance(get_llm_client(), DeterministicNarrator)


def test_gemini_configures_sdk_transport_timeout(monkeypatch) -> None:
    pytest.importorskip("google.genai")
    from app.intelligence.llm_client import GeminiClient

    monkeypatch.setattr(settings, "llm_timeout_seconds", 7)
    client = GeminiClient("dummy-key")

    assert client._timeout == 7
    assert client._client._api_client._http_options.timeout == 7000


@pytest.mark.asyncio
async def test_gemini_client_success_and_failure_paths() -> None:
    pytest.importorskip("google.genai")
    from app.intelligence.llm_client import GeminiClient

    client = GeminiClient("dummy-key")

    class _Resp:
        text = "gemini prose"

    # Success → returns model text.
    async def _success(**_k):
        return _Resp()

    client._client.aio.models.generate_content = _success
    assert await client.generate("sys", "prompt", "fb") == "gemini prose"

    # Empty text → falls back.
    class _Empty:
        text = ""

    async def _empty(**_k):
        return _Empty()

    client._client.aio.models.generate_content = _empty
    assert await client.generate("sys", "prompt", "fb") == "fb"

    # Exception (network/quota) → retries then falls back, never raises.
    async def _boom(**_k):
        raise RuntimeError("api down")

    client._client.aio.models.generate_content = _boom
    assert await client.generate("sys", "prompt", "fb") == "fb"


@pytest.mark.asyncio
async def test_gemini_timeout_retries_then_falls_back() -> None:
    pytest.importorskip("google.genai")
    from app.intelligence.llm_client import GeminiClient

    client = GeminiClient("dummy-key")
    client._timeout = 0.01
    client._retries = 2
    calls = 0

    async def _hang(**_k):
        nonlocal calls
        calls += 1
        await asyncio.sleep(1)

    client._client.aio.models.generate_content = _hang

    assert await client.generate("sys", "prompt", "fallback") == "fallback"
    assert calls == 2


@pytest.mark.asyncio
async def test_gemini_generation_does_not_block_event_loop() -> None:
    pytest.importorskip("google.genai")
    from app.intelligence.llm_client import GeminiClient

    client = GeminiClient("dummy-key")
    started = asyncio.Event()
    release = asyncio.Event()

    class _Resp:
        text = "async prose"

    async def _delayed(**_k):
        started.set()
        await release.wait()
        return _Resp()

    client._client.aio.models.generate_content = _delayed
    generation = asyncio.create_task(client.generate("sys", "prompt", "fallback"))

    await asyncio.wait_for(started.wait(), timeout=0.1)
    # This coroutine can run while the provider request is in flight.
    await asyncio.sleep(0)
    assert not generation.done()
    release.set()
    assert await generation == "async prose"


@pytest.mark.asyncio
async def test_gemini_retries_rejected_prose_then_returns_grounded_output() -> None:
    pytest.importorskip("google.genai")
    from app.intelligence.llm_client import GeminiClient

    rec = Recommendation(
        symbol="AAA.NS",
        name="AAA",
        sector="Tech",
        action="watch",
        score=0.4,
        confidence=70,
        evidence=["RSI at 60 (bullish momentum)"],
        risks=["Standard market risk applies"],
    )
    prompt, fallback = pb.recommendation_explanation(rec)
    responses = iter(
        [
            "AAA.NS will reach 999.",
            (
                "Watch AAA.NS with 70% confidence because RSI at 60 shows "
                "bullish momentum. Standard market risk applies."
            ),
        ]
    )
    calls = 0

    class _Resp:
        def __init__(self, text: str) -> None:
            self.text = text

    async def _response(**_k):
        nonlocal calls
        calls += 1
        return _Resp(next(responses))

    client = GeminiClient("dummy-key")
    client._retries = 2
    client._client.aio.models.generate_content = _response

    result = await generate_grounded(client, "system", prompt, fallback)
    assert result.startswith("Watch AAA.NS with 70% confidence")
    assert calls == 2


@pytest.mark.asyncio
async def test_post_generation_guard_falls_back_for_noncompliant_adapter() -> None:
    rec = Recommendation(
        symbol="AAA.NS",
        name="AAA",
        sector="Tech",
        action="watch",
        score=0.4,
        confidence=70,
        evidence=["RSI at 60 (bullish momentum)"],
        risks=["Standard market risk applies"],
    )
    prompt, fallback = pb.recommendation_explanation(rec)

    class _NoncompliantClient:
        async def generate(self, system, prompt, fallback, validator=None):
            return "AAA.NS will reach 999."

    result = await generate_grounded(
        _NoncompliantClient(), "system", prompt, fallback
    )
    assert result == fallback
