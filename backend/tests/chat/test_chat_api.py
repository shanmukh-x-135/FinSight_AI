"""Chat API, persistence, ownership, streaming, and grounding tests."""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from app.chat.dependencies import get_chat_llm_client
from app.intelligence.generation import GenerationMetadata, GenerationResult, TokenUsage
from tests.chat.conftest import authenticated_headers, provision_personal_context


class UnsupportedAdviceLLM:
    async def generate(self, system, prompt, fallback, validator=None) -> str:
        return "Buy now at 999 because it will rise."


class GroundedGeminiLLM:
    text = (
        "Market breadth has 1 advancer, 1 decliner, and 1 unchanged. "
        "Source: Market analytics (2026-08-04). "
        "Risk: End-of-day data may not reflect intraday moves."
    )

    async def generate(
        self, system, prompt, fallback, validator=None
    ) -> GenerationResult:
        if validator:
            assert validator(self.text).valid
        return GenerationResult(
            text=self.text,
            metadata=GenerationMetadata(
                configured_backend="GeminiClient",
                backend="gemini",
                requested_model="gemini-3.6-flash",
                model_version="gemini-3.6-flash-001",
                response_id="response-grounded",
                finish_reason="STOP",
                attempt_count=1,
                provider_response_count=1,
                fallback_used=False,
                latency_ms=25,
                usage=TokenUsage(
                    prompt_tokens=100,
                    candidate_tokens=30,
                    total_tokens=130,
                ),
            ),
        )


class ContradictoryConfidenceGeminiLLM(GroundedGeminiLLM):
    text = GroundedGeminiLLM.text + " Confidence is 1%."

    async def generate(
        self, system, prompt, fallback, validator=None
    ) -> GenerationResult:
        return await super().generate(system, prompt, fallback, validator=None)


def _events(body: str) -> list[tuple[str, dict]]:
    parsed: list[tuple[str, dict]] = []
    for block in body.strip().split("\n\n"):
        lines = block.splitlines()
        event = next(line[7:] for line in lines if line.startswith("event: "))
        data = next(line[6:] for line in lines if line.startswith("data: "))
        parsed.append((event, json.loads(data)))
    return parsed


@pytest.mark.asyncio
async def test_chat_requires_authentication(client: AsyncClient) -> None:
    response = await client.post("/api/v1/chat", json={"message": "How is the market?"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_rejects_blank_message(
    client: AsyncClient, seeded_chat_market: None
) -> None:
    headers = await authenticated_headers(client, "blank@example.com")
    response = await client.post("/api/v1/chat", json={"message": "   "}, headers=headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_answers_from_personal_portfolio_and_watchlist(
    client: AsyncClient, seeded_chat_market: None
) -> None:
    headers = await authenticated_headers(client, "chat@example.com")
    await provision_personal_context(client, headers)

    response = await client.post(
        "/api/v1/chat",
        json={"message": "How are my portfolio and watchlist doing?"},
        headers=headers,
    )

    assert response.status_code == 200
    exchange = response.json()["data"]
    assistant = exchange["assistant"]
    assert exchange["user"]["content"] == "How are my portfolio and watchlist doing?"
    assert "AAA.NS" in assistant["content"]
    assert "BBB.NS" in assistant["content"]
    assert "1 tracked stock: BBB.NS" in assistant["content"]
    assert assistant["evidence"]
    assert assistant["risks"]
    assert assistant["confidence"] >= 60
    assert assistant["generation"]["backend"] == "deterministic"
    assert assistant["generation"]["fallback_used"] is False
    assert {source["kind"] for source in assistant["sources"]} == {
        "portfolio",
        "watchlist",
    }

    history = await client.get("/api/v1/chat/history", headers=headers)
    assert history.status_code == 200
    messages = history.json()["data"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["evidence"] == assistant["evidence"]
    assert messages[1]["sources"] == assistant["sources"]
    assert messages[1]["generation"] == assistant["generation"]


@pytest.mark.asyncio
async def test_chat_stream_reconstructs_validated_persisted_answer(
    client: AsyncClient, seeded_chat_market: None
) -> None:
    headers = await authenticated_headers(client, "stream@example.com")
    response = await client.post(
        "/api/v1/chat?stream=true",
        json={"message": "What does today's market breadth show?"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response.text)
    assert events[0][0] == "meta"
    assert events[-1][0] == "complete"
    deltas = [data["delta"] for event, data in events if event == "chunk"]
    assert len(deltas) > 1
    completed = events[-1][1]["assistant"]
    assert "".join(deltas) == completed["content"]
    assert completed["evidence"]
    assert completed["sources"][0]["kind"] == "market"
    assert completed["generation"]["backend"] == "deterministic"

    history = (await client.get("/api/v1/chat/history", headers=headers)).json()["data"]
    assert history[-1]["content"] == completed["content"]


@pytest.mark.asyncio
async def test_valid_gemini_chat_omitting_confidence_keeps_app_confidence(
    client: AsyncClient, test_app, seeded_chat_market: None
) -> None:
    test_app.dependency_overrides[get_chat_llm_client] = lambda: GroundedGeminiLLM()
    headers = await authenticated_headers(client, "gemini-grounded@example.com")

    response = await client.post(
        "/api/v1/chat",
        json={"message": "What moved the market today?"},
        headers=headers,
    )

    assert response.status_code == 200
    assistant = response.json()["data"]["assistant"]
    assert assistant["content"] == GroundedGeminiLLM.text
    assert assistant["confidence"] == 55
    assert "confidence" not in assistant["content"].lower()
    assert assistant["generation"]["backend"] == "gemini"
    assert assistant["generation"]["fallback_used"] is False
    assert assistant["generation"]["model_version"] == "gemini-3.6-flash-001"
    assert assistant["generation"]["provider_response_count"] == 1
    assert assistant["generation"]["usage"]["total_tokens"] == 130


@pytest.mark.asyncio
async def test_contradictory_gemini_confidence_uses_deterministic_fallback_value(
    client: AsyncClient, test_app, seeded_chat_market: None
) -> None:
    test_app.dependency_overrides[get_chat_llm_client] = lambda: (
        ContradictoryConfidenceGeminiLLM()
    )
    headers = await authenticated_headers(client, "gemini-confidence@example.com")

    response = await client.post(
        "/api/v1/chat",
        json={"message": "What moved the market today?"},
        headers=headers,
    )

    assert response.status_code == 200
    assistant = response.json()["data"]["assistant"]
    assert assistant["confidence"] == 55
    assert "Confidence 55%" in assistant["content"]
    assert "Confidence is 1%" not in assistant["content"]
    assert assistant["generation"]["backend"] == "deterministic"
    assert assistant["generation"]["fallback_used"] is True
    assert assistant["generation"]["model_version"] == "gemini-3.6-flash-001"


@pytest.mark.asyncio
async def test_successful_gemini_chat_stream_completes_with_metadata(
    client: AsyncClient, test_app, seeded_chat_market: None
) -> None:
    test_app.dependency_overrides[get_chat_llm_client] = lambda: GroundedGeminiLLM()
    headers = await authenticated_headers(client, "gemini-stream@example.com")

    response = await client.post(
        "/api/v1/chat?stream=true",
        json={"message": "Summarise today's market using the available evidence."},
        headers=headers,
    )

    assert response.status_code == 200
    events = _events(response.text)
    assert events[-1][0] == "complete"
    completed = events[-1][1]["assistant"]
    deltas = [data["delta"] for event, data in events if event == "chunk"]
    assert "".join(deltas) == GroundedGeminiLLM.text
    assert completed["confidence"] == 55
    assert completed["generation"]["backend"] == "gemini"
    assert completed["generation"]["fallback_used"] is False
    assert completed["generation"]["response_id"] == "response-grounded"


@pytest.mark.asyncio
async def test_chat_rejects_unsupported_model_advice_and_uses_grounded_fallback(
    client: AsyncClient, test_app, seeded_chat_market: None
) -> None:
    test_app.dependency_overrides[get_chat_llm_client] = lambda: UnsupportedAdviceLLM()
    headers = await authenticated_headers(client, "grounded@example.com")

    response = await client.post(
        "/api/v1/chat",
        json={"message": "Will the market reach 999?"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["assistant"]["generation"]["fallback_used"] is True
    content = response.json()["data"]["assistant"]["content"]
    assert "Buy now" not in content
    assert "999" not in content
    assert "Market breadth" in content


@pytest.mark.asyncio
async def test_chat_history_is_user_scoped_and_delete_isolated(
    client: AsyncClient, seeded_chat_market: None
) -> None:
    first = await authenticated_headers(client, "first-chat@example.com")
    second = await authenticated_headers(client, "second-chat@example.com")
    await provision_personal_context(client, first)
    await client.post(
        "/api/v1/chat",
        json={"message": "Summarize my portfolio."},
        headers=first,
    )

    second_history = await client.get("/api/v1/chat/history", headers=second)
    assert second_history.json()["data"] == []
    second_answer = await client.post(
        "/api/v1/chat",
        json={"message": "Summarize my portfolio."},
        headers=second,
    )
    assert (
        "No portfolio is currently available"
        in second_answer.json()["data"]["assistant"]["content"]
    )

    deleted = await client.delete("/api/v1/chat/history", headers=second)
    assert deleted.json()["data"]["deleted"] == 2
    first_history = await client.get("/api/v1/chat/history", headers=first)
    assert len(first_history.json()["data"]) == 2

    first_deleted = await client.delete("/api/v1/chat/history", headers=first)
    assert first_deleted.json()["data"]["deleted"] == 2
    assert (await client.get("/api/v1/chat/history", headers=first)).json()["data"] == []


@pytest.mark.asyncio
async def test_chat_handles_an_empty_portfolio_without_inventing_metrics(
    client: AsyncClient, seeded_chat_market: None
) -> None:
    headers = await authenticated_headers(client, "empty-portfolio@example.com")
    created = await client.post(
        "/api/v1/portfolios", json={"name": "Empty"}, headers=headers
    )
    assert created.status_code == 201

    response = await client.post(
        "/api/v1/chat",
        json={"message": "What about my portfolio?"},
        headers=headers,
    )

    assert response.status_code == 200
    assistant = response.json()["data"]["assistant"]
    assert "does not contain any holdings" in assistant["content"]
    assert "₹0" not in assistant["content"]
