"""Tests for the LLM client abstraction (narrator default + Gemini fallback)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.intelligence import prompt_builder as pb
from app.intelligence.generation import GenerationBudget
from app.intelligence.llm_client import (
    DeterministicNarrator,
    generate_grounded,
    generate_grounded_result,
    get_llm_client,
)
from app.intelligence.recommendation_engine import Recommendation
from config.settings import Settings, settings


def test_production_default_uses_current_stable_gemini_model() -> None:
    configured = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost/finsight",
        _env_file=None,
    )
    assert configured.llm_model == "gemini-3.6-flash"
    assert configured.llm_max_output_tokens == 1024
    assert configured.llm_request_budget_seconds == 45
    assert configured.llm_max_provider_calls == 20


@pytest.mark.asyncio
async def test_narrator_returns_fallback() -> None:
    result = await DeterministicNarrator().generate("sys", "prompt", "the fallback")
    assert result.text == "the fallback"
    assert result.metadata.backend == "deterministic"
    assert result.metadata.fallback_used is False


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
        model_version = "gemini-3.6-flash-001"
        response_id = "response-1"
        create_time = datetime(2026, 8, 11, tzinfo=timezone.utc)
        candidates = [SimpleNamespace(finish_reason="STOP")]
        usage_metadata = SimpleNamespace(
            prompt_token_count=10,
            candidates_token_count=4,
            total_token_count=14,
            cached_content_token_count=2,
            thoughts_token_count=1,
        )

    # Success → returns model text.
    request: dict = {}

    async def _success(**kwargs):
        request.update(kwargs)
        return _Resp()

    client._client.aio.models.generate_content = _success
    result = await client.generate("sys", "prompt", "fb")
    assert result.text == "gemini prose"
    assert result.metadata.backend == "gemini"
    assert result.metadata.model_version == "gemini-3.6-flash-001"
    assert result.metadata.response_id == "response-1"
    assert result.metadata.finish_reason == "STOP"
    assert result.metadata.usage.total_tokens == 14
    assert request["contents"] == "prompt"
    assert request["config"].system_instruction == "sys"
    assert request["config"].candidate_count == 1
    assert request["config"].max_output_tokens == settings.llm_max_output_tokens

    # Empty text → falls back.
    class _Empty:
        text = ""

    async def _empty(**_k):
        return _Empty()

    client._client.aio.models.generate_content = _empty
    result = await client.generate("sys", "prompt", "fb")
    assert result.text == "fb"
    assert result.metadata.backend == "deterministic"
    assert result.metadata.fallback_used is True

    # Exception (network/quota) → retries then falls back, never raises.
    async def _boom(**_k):
        raise RuntimeError("api down")

    client._client.aio.models.generate_content = _boom
    result = await client.generate("sys", "prompt", "fb")
    assert result.text == "fb"
    assert result.metadata.attempt_count == settings.llm_max_retries
    assert result.metadata.provider_response_count == 0


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

    result = await client.generate("sys", "prompt", "fallback")
    assert result.text == "fallback"
    assert result.metadata.fallback_used is True
    assert result.metadata.attempt_count == 2
    assert calls == 2


@pytest.mark.asyncio
async def test_shared_request_budget_caps_provider_attempts() -> None:
    pytest.importorskip("google.genai")
    from app.intelligence.llm_client import GeminiClient

    calls = 0

    async def _boom(**_kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("provider unavailable")

    client = GeminiClient("dummy-key")
    client._retries = 3
    client._client.aio.models.generate_content = _boom
    budget = GenerationBudget(total_seconds=2, max_provider_calls=2)
    prompt, fallback = pb.market_section(
        {
            "breadth": {"advancers": 1, "decliners": 1, "unchanged": 0},
            "gainers": [],
            "losers": [],
        }
    )

    results = await asyncio.gather(
        *(
            generate_grounded_result(
                client,
                "system",
                prompt,
                fallback,
                budget=budget,
            )
            for _ in range(3)
        )
    )

    assert calls == 2
    assert budget.provider_calls == 2
    assert sum(result.metadata.attempt_count for result in results) == 2
    assert all(result.metadata.fallback_used for result in results)


@pytest.mark.asyncio
async def test_shared_request_deadline_bounds_provider_latency() -> None:
    pytest.importorskip("google.genai")
    from app.intelligence.llm_client import GeminiClient

    async def _hang(**_kwargs):
        await asyncio.sleep(1)

    client = GeminiClient("dummy-key")
    client._timeout = 1
    client._retries = 3
    client._client.aio.models.generate_content = _hang
    budget = GenerationBudget(total_seconds=0.02, max_provider_calls=5)
    prompt, fallback = pb.market_section(
        {
            "breadth": {"advancers": 1, "decliners": 1, "unchanged": 0},
            "gainers": [],
            "losers": [],
        }
    )
    started = asyncio.get_running_loop().time()

    result = await generate_grounded_result(
        client, "system", prompt, fallback, budget=budget
    )

    assert asyncio.get_running_loop().time() - started < 0.25
    assert result.metadata.fallback_used is True
    assert result.metadata.attempt_count == 1
    assert budget.provider_calls == 1


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
    result = await generation
    assert result.text == "async prose"
    assert result.metadata.latency_ms >= 0


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
async def test_gemini_chat_omitting_confidence_is_accepted_on_first_response() -> None:
    pytest.importorskip("google.genai")
    from app.intelligence.llm_client import GeminiClient

    facts = {
        "question": "See the untrusted user question above.",
        "context": {"market": {"breadth": {"advancers": 3, "decliners": 2}}},
        "evidence": ["Market breadth has 3 advancers and 2 decliners."],
        "confidence": 65,
        "sources": [
            {"kind": "market", "label": "Market analytics", "reference": "/market"}
        ],
        "risks": ["End-of-day data may not reflect intraday moves."],
    }
    prompt, fallback = pb.chat_response(
        question="What moved the market?",
        recent_questions=[],
        facts=facts,
        fallback=(
            "Market breadth has 3 advancers and 2 decliners. Confidence 65%. "
            "Sources: Market analytics. "
            "Risks: End-of-day data may not reflect intraday moves."
        ),
    )
    provider_text = (
        "Market analytics shows 3 advancers and 2 decliners. "
        "End-of-day data may not reflect intraday moves."
    )
    calls = 0

    async def _response(**_kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(
            text=provider_text,
            model_version="gemini-3.6-flash-001",
            response_id="response-chat",
            create_time=None,
            candidates=[SimpleNamespace(finish_reason="STOP")],
            usage_metadata=SimpleNamespace(
                prompt_token_count=20,
                candidates_token_count=10,
                total_token_count=30,
                cached_content_token_count=None,
                thoughts_token_count=None,
            ),
        )

    client = GeminiClient("dummy-key")
    client._client.aio.models.generate_content = _response

    result = await generate_grounded_result(client, "system", prompt, fallback)

    assert result.text == provider_text
    assert calls == 1
    assert result.metadata.backend == "gemini"
    assert result.metadata.provider_response_count == 1
    assert result.metadata.fallback_used is False
    assert result.metadata.model_version == "gemini-3.6-flash-001"
    assert result.metadata.usage.total_tokens == 30


@pytest.mark.asyncio
async def test_gemini_metadata_aggregates_usage_across_rejected_attempts() -> None:
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
    texts = iter(
        [
            "AAA.NS will reach 999.",
            (
                "Watch AAA.NS with 70% confidence because RSI at 60 shows "
                "bullish momentum. Standard market risk applies."
            ),
        ]
    )
    response_number = 0

    async def _response(**_kwargs):
        nonlocal response_number
        response_number += 1
        return SimpleNamespace(
            text=next(texts),
            model_version="gemini-3.6-flash-001",
            response_id=f"response-{response_number}",
            create_time=None,
            candidates=[SimpleNamespace(finish_reason="STOP")],
            usage_metadata=SimpleNamespace(
                prompt_token_count=10,
                candidates_token_count=response_number,
                total_token_count=10 + response_number,
                cached_content_token_count=None,
                thoughts_token_count=None,
            ),
        )

    client = GeminiClient("dummy-key")
    client._retries = 2
    client._client.aio.models.generate_content = _response

    result = await generate_grounded_result(client, "system", prompt, fallback)

    assert result.metadata.attempt_count == 2
    assert result.metadata.provider_response_count == 2
    assert result.metadata.response_id == "response-2"
    assert result.metadata.usage.prompt_tokens == 20
    assert result.metadata.usage.candidate_tokens == 3
    assert result.metadata.usage.total_tokens == 23
    assert result.metadata.fallback_used is False


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

    result = await generate_grounded(_NoncompliantClient(), "system", prompt, fallback)
    assert result == fallback


@pytest.mark.asyncio
async def test_rejection_logs_category_without_provider_claim_value(caplog) -> None:
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

    class _UnsupportedNumberClient:
        async def generate(self, system, prompt, fallback, validator=None):
            return (
                "Watch AAA.NS with 70% confidence and RSI at 60, plus 999. "
                "Standard market risk applies."
            )

    result = await generate_grounded_result(
        _UnsupportedNumberClient(), "system", prompt, fallback
    )

    assert result.metadata.fallback_used is True
    rejection = next(
        record
        for record in caplog.records
        if record.getMessage() == "llm_output_rejected_using_fallback"
    )
    assert rejection.reason == "unsupported numeric claim"
    # Inspect only application-controlled log fields. Standard LogRecord
    # metadata contains timing/thread numbers that can coincidentally include
    # the provider claim (for example ``created=19990...``), making an
    # otherwise-correct redaction test nondeterministic.
    application_fields = {
        "message": rejection.getMessage(),
        "reason": rejection.reason,
    }
    assert "999" not in str(application_fields)
