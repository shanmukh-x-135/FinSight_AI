"""Controlled tests for deterministic news enrichment rules."""

from app.news.classification import (
    classify_event,
    evidence_excerpt,
    sentiment_confidence,
)
from app.news.tagging import match_article_entities


def test_event_classification_is_explainable_and_bounded() -> None:
    result = classify_event(
        "Reliance quarterly results beat estimates",
        "Profit and revenue rose during the quarter.",
    )
    assert result.category == "Earnings"
    assert result.driver == "Reported financial performance"
    assert 0.5 <= result.confidence < 1


def test_unmatched_event_remains_explicitly_unclassified() -> None:
    result = classify_event("Company shares traded on Friday", "")
    assert result.category == "Other"
    assert result.confidence < 0.5


def test_evidence_excerpt_strips_markup_and_is_bounded() -> None:
    result = evidence_excerpt("Headline", "<p>Verified &amp; traceable</p> " + "x" * 500)
    assert "<p>" not in result
    assert "Verified & traceable" in result
    assert len(result) == 320


def test_neutral_without_direction_is_not_reported_as_certain() -> None:
    assert sentiment_confidence(score=0, positive=0, negative=0, neutral=1) == 0.6


def test_entity_match_returns_alias_and_confidence() -> None:
    matches = match_article_entities(
        "Tata Consultancy Services wins contract",
        "",
        {1: {"TCS", "TATA CONSULTANCY SERVICES"}},
    )
    assert matches[1].alias == "TATA CONSULTANCY SERVICES"
    assert matches[1].confidence == 0.95
