"""Integration tests for report generation and recommendations.

Uses the default DeterministicNarrator, so output is fully reproducible — which
lets us assert grounding, structure, explainability, and consistency.
"""

from __future__ import annotations

import asyncio
import copy

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.generation import GenerationMetadata, GenerationResult, TokenUsage
from app.intelligence.service import IntelligenceService
from app.portfolio.models import Portfolio, PortfolioItem


@pytest.mark.asyncio
async def test_report_has_required_sections_and_evidence(
    db_session: AsyncSession, seed_market: dict[str, int]
) -> None:
    report = await IntelligenceService(db_session).generate_report(user_id=None)
    s = report.sections

    # Required sections (validate_report would have raised otherwise).
    assert s["market_summary"]["narrative"].strip()
    assert s["executive_summary"].strip()
    assert isinstance(s["recommendations"], list)
    # No history index / no portfolio in this scenario → those sections absent.
    assert "historical_summary" not in s
    assert "portfolio_summary" not in s

    # AAA is the strong bullish candidate → on the watchlist with full evidence.
    watch = {r["symbol"]: r for r in s["recommendations"]}
    assert "AAA.NS" in watch
    aaa = watch["AAA.NS"]
    assert aaa["evidence"] and aaa["risks"] and aaa["explanation"].strip()
    assert aaa["confidence"] is not None
    # BBB (bearish) is a risk alert, not a watch recommendation.
    assert "BBB.NS" in {r["symbol"] for r in s["risk_alerts"]}

    assert s["meta"]["llm_backend"] == "DeterministicNarrator"
    assert s["meta"]["prompt_version"]
    generation = s["meta"]["generation"]
    assert generation["configured_backend"] == "DeterministicNarrator"
    assert generation["actual_backends"] == ["deterministic"]
    assert generation["fallback_count"] == 0
    assert generation["generation_count"] == len(generation["items"])
    assert generation["generation_count"] >= 4
    assert all(item["purpose"] for item in generation["items"])


@pytest.mark.asyncio
async def test_report_narrative_is_grounded(
    db_session: AsyncSession, seed_market: dict[str, int]
) -> None:
    report = await IntelligenceService(db_session).generate_report(user_id=None)
    s = report.sections
    # Market narrative reflects real breadth: 1 advancer (AAA), 1 decliner (BBB).
    assert "1 advancers" in s["market_summary"]["narrative"]
    assert "1 decliners" in s["market_summary"]["narrative"]
    # A recommendation's explanation contains its own evidence (grounded by construction).
    aaa = next(r for r in s["recommendations"] if r["symbol"] == "AAA.NS")
    assert aaa["evidence"][0] in aaa["explanation"]


@pytest.mark.asyncio
async def test_report_is_reproducible(
    db_session: AsyncSession, seed_market: dict[str, int]
) -> None:
    svc = IntelligenceService(db_session)
    first = copy.deepcopy((await svc.generate_report(user_id=None)).sections)
    second = copy.deepcopy((await svc.generate_report(user_id=None)).sections)
    # Everything except the generated_at timestamp is identical.
    first["meta"].pop("generated_at")
    second["meta"].pop("generated_at")
    assert first == second


@pytest.mark.asyncio
async def test_report_provenance_distinguishes_gemini_from_partial_fallback(
    db_session: AsyncSession, seed_market: dict[str, int]
) -> None:
    class _MixedClient:
        calls = 0

        async def generate(self, system, prompt, fallback, validator=None):
            self.calls += 1
            if self.calls == 1:
                metadata = GenerationMetadata(
                    configured_backend=type(self).__name__,
                    backend="gemini",
                    requested_model="gemini-3.6-flash",
                    model_version="gemini-3.6-flash-001",
                    response_id="response-1",
                    finish_reason="STOP",
                    attempt_count=1,
                    provider_response_count=1,
                    usage=TokenUsage(total_tokens=14),
                )
            else:
                metadata = GenerationMetadata(
                    configured_backend=type(self).__name__,
                    backend="deterministic",
                    requested_model="gemini-3.6-flash",
                    attempt_count=2,
                    fallback_used=True,
                )
            return GenerationResult(text=fallback, metadata=metadata)

    report = await IntelligenceService(db_session, _MixedClient()).generate_report(None)
    meta = report.sections["meta"]
    generation = meta["generation"]

    assert meta["llm_backend"] == "Gemini + deterministic fallback"
    assert generation["actual_backends"] == ["deterministic", "gemini"]
    assert generation["fallback_count"] == generation["generation_count"] - 1
    assert generation["model_versions"] == ["gemini-3.6-flash-001"]
    assert generation["usage"]["total_tokens"] == 14


@pytest.mark.asyncio
async def test_report_generates_independent_narratives_concurrently(
    db_session: AsyncSession, seed_market: dict[str, int]
) -> None:
    class _ConcurrentClient:
        active = 0
        max_active = 0

        async def generate(self, system, prompt, fallback, validator=None):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return fallback

    client = _ConcurrentClient()
    report = await IntelligenceService(db_session, client).generate_report(None)

    assert client.max_active > 1
    assert report.sections["meta"]["generation"]["generation_count"] >= 4


@pytest.mark.asyncio
async def test_report_includes_portfolio_when_present(
    db_session: AsyncSession, seed_market: dict[str, int]
) -> None:
    # A user with a holding → portfolio_summary appears.
    from app.auth.models import User

    user = User(email="rep@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    pf = Portfolio(user_id=user.id, name="P")
    db_session.add(pf)
    await db_session.flush()
    db_session.add(
        PortfolioItem(
            portfolio_id=pf.id,
            stock_id=seed_market["AAA.NS"],
            quantity=10,
            avg_buy_price=100,
        )
    )
    await db_session.commit()

    report = await IntelligenceService(db_session).generate_report(user_id=user.id)
    assert report.sections["portfolio_summary"]["narrative"].strip()
    assert report.user_id == user.id


@pytest.mark.asyncio
async def test_get_recommendations(
    db_session: AsyncSession, seed_market: dict[str, int]
) -> None:
    data = await IntelligenceService(db_session).get_recommendations(user_id=None)
    assert "AAA.NS" in {r["symbol"] for r in data["watchlist"]}
    assert all(r["explanation"].strip() for r in data["watchlist"])
    assert data["generation"]["actual_backends"] == ["deterministic"]
