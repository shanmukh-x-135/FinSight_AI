"""Phase 10E representative-query retrieval and grounding benchmark."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.chat.service import _build_draft
from app.intelligence.context_builder import RagContext
from app.intelligence.recommendation_engine import CandidateInput

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "phase10e_golden_queries.json"


@pytest.fixture
def golden_context() -> RagContext:
    return RagContext(
        market={
            "breadth": {
                "advancers": 31,
                "decliners": 18,
                "unchanged": 1,
                "advance_decline_ratio": 1.7222,
            },
            "gainers": [
                {
                    "symbol": "RELIANCE.NS",
                    "change_percent": 2.5,
                    "close": 1_400.0,
                    "date": "2026-08-21",
                },
            ],
            "losers": [
                {
                    "symbol": "BEAR.NS",
                    "change_percent": -2.0,
                    "close": 100.0,
                    "date": "2026-08-21",
                },
            ],
        },
        portfolio={
            "total_value": 150_000.0,
            "total_return_percent": 8.0,
            "health_score": 72.0,
            "risk_level": "moderate",
            "number_of_holdings": 2,
            "number_of_sectors": 2,
            "top_holding_weight_percent": 70.0,
            "diversification_score": 42.0,
            "volatility_percent": 2.1,
            "valuation_complete": True,
            "unpriced_symbols": [],
            "sector_allocation": [
                {"sector": "Energy", "value": 105_000.0, "weight_percent": 70.0}
            ],
            "holdings": [
                {"symbol": "RELIANCE.NS"},
                {"symbol": "BEAR.NS"},
            ],
        },
        watchlist=[{"symbol": "RELIANCE.NS", "change_percent": 2.5}],
        history={
            "query_date": "2026-08-21",
            "statistics": {
                "bullish_probability": 0.6,
                "sample_size": 5,
            },
            "similar_sessions": [{"date": "2026-08-17"}],
        },
        news={
            "notable": [
                {
                    "title": "AAA files exchange update",
                    "source": "Exchange RSS",
                    "url": "https://example.test/aaa-update",
                    "published_at": "2026-08-21T12:00:00+00:00",
                    "sentiment_label": "neutral",
                    "sentiment_score": 0.0,
                    "tags": ["AAA.NS"],
                }
            ]
        },
        candidates=[
            CandidateInput(
                symbol="RELIANCE.NS",
                name="Reliance Industries",
                sector="Energy",
                price=1_400.0,
                change_percent=2.5,
                rsi=64.0,
                ema20_distance_pct=3.0,
                ema50_distance_pct=4.0,
                macd_hist=1.0,
                atr_pct=1.5,
                sentiment=0.3,
                sector_change_percent=1.2,
                hist_bullish_probability=0.6,
                hist_sample_size=5,
            ),
            CandidateInput(
                symbol="BEAR.NS",
                name="Bear Industries",
                sector="Metals",
                price=100.0,
                change_percent=-2.0,
                rsi=32.0,
                ema20_distance_pct=-4.0,
                ema50_distance_pct=-5.0,
                macd_hist=-1.0,
                atr_pct=3.0,
                sentiment=-0.5,
                sector_change_percent=-1.5,
                hist_bullish_probability=0.4,
                hist_sample_size=5,
            ),
            CandidateInput(
                symbol="SPARSE.NS",
                name="Sparse Industries",
                sector=None,
                price=50.0,
                change_percent=None,
                rsi=None,
                ema20_distance_pct=None,
                ema50_distance_pct=None,
                macd_hist=None,
                atr_pct=None,
                sentiment=None,
                sector_change_percent=None,
            ),
        ],
    )


def _load_queries() -> list[dict]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert payload["benchmark_version"] == "1.0"
    assert len(payload["queries"]) == 10
    return payload["queries"]


@pytest.mark.parametrize("scenario", _load_queries(), ids=lambda item: item["id"])
def test_representative_query_is_grounded_in_expected_slices(
    scenario: dict, golden_context: RagContext
) -> None:
    draft = _build_draft(
        scenario["question"], scenario["recent_questions"], golden_context
    )
    evidence = " | ".join(draft.evidence)
    risks = " | ".join(draft.risks)

    assert [source.kind for source in draft.sources] == scenario["source_kinds"]
    assert all(fragment in evidence for fragment in scenario["evidence_contains"])
    assert all(fragment in risks for fragment in scenario.get("risk_contains", []))
    assert draft.confidence <= 85
    assert scenario["question"] not in json.dumps(draft.facts)
    assert "investment advice" in draft.fallback


def test_current_prices_dates_and_news_url_are_exposed_as_evidence(
    golden_context: RagContext,
) -> None:
    draft = _build_draft("Generate today's EOD research brief.", [], golden_context)
    evidence = " | ".join(draft.evidence)
    news_source = next(source for source in draft.sources if source.kind == "news")

    assert "close ₹1,400" in evidence
    assert "2026-08-21" in evidence
    assert "published 2026-08-21T12:00:00+00:00" in evidence
    assert news_source.reference == "https://example.test/aaa-update"


def test_unknown_company_question_does_not_invent_company_facts(
    golden_context: RagContext,
) -> None:
    draft = _build_draft("Why is UNKNOWNCO moving?", [], golden_context)

    assert "company" not in draft.facts["context"]
    assert all("UNKNOWNCO" not in item for item in draft.evidence)


def test_company_uses_current_market_date_when_not_a_top_mover(
    golden_context: RagContext,
) -> None:
    golden_context.market["gainers"][0]["symbol"] = "OTHER.NS"

    draft = _build_draft("Why is RELIANCE moving?", [], golden_context)

    assert any(
        "RELIANCE.NS closed at ₹1,400 and moved +2.50% on 2026-08-21" in item
        for item in draft.evidence
    )


def test_unsafe_news_reference_is_not_exposed(
    golden_context: RagContext,
) -> None:
    assert golden_context.news["notable"]
    golden_context.news["notable"][0]["url"] = "javascript:alert(1)"

    draft = _build_draft("What news is relevant?", [], golden_context)

    assert draft.sources[0].kind == "news"
    assert draft.sources[0].reference == "/market"
