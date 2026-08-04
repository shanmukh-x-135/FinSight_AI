"""Tests for explainability validation (evidence/confidence/risks/narrative)."""

from __future__ import annotations

import pytest

from app.intelligence.explainability import (
    ExplainabilityError,
    validate_grounded_narrative,
    validate_recommendation,
    validate_report,
)
from app.intelligence.prompt_builder import market_section, recommendation_explanation
from app.intelligence.recommendation_engine import Recommendation


def _rec(**over) -> dict:
    base = {
        "symbol": "AAA", "evidence": ["RSI at 60"], "confidence": 70,
        "risks": ["Standard market risk applies"], "explanation": "Watch AAA.",
    }
    base.update(over)
    return base


def test_valid_recommendation_passes() -> None:
    validate_recommendation(_rec())  # no raise


@pytest.mark.parametrize("field", ["evidence", "risks"])
def test_missing_list_fields_raise(field: str) -> None:
    with pytest.raises(ExplainabilityError):
        validate_recommendation(_rec(**{field: []}))


def test_missing_confidence_raises() -> None:
    with pytest.raises(ExplainabilityError):
        validate_recommendation(_rec(confidence=None))


def test_missing_explanation_raises() -> None:
    with pytest.raises(ExplainabilityError):
        validate_recommendation(_rec(explanation="  "))


def test_report_requires_market_recommendations_and_executive() -> None:
    good = {
        "market_summary": {"narrative": "Market was mixed."},
        "recommendations": [_rec()],
        "executive_summary": "Summary.",
    }
    validate_report(good)  # no raise

    with pytest.raises(ExplainabilityError):
        validate_report({**good, "market_summary": {"narrative": ""}})
    with pytest.raises(ExplainabilityError):
        validate_report({k: v for k, v in good.items() if k != "recommendations"})
    with pytest.raises(ExplainabilityError):
        validate_report({**good, "executive_summary": ""})


def test_market_narrative_is_checked_against_prompt_facts() -> None:
    prompt, _fallback = market_section(
        {
            "breadth": {
                "advancers": 3,
                "decliners": 1,
                "unchanged": 0,
                "total": 4,
                "advance_decline_ratio": 3.0,
            },
            "gainers": [{"symbol": "AAA.NS", "change_percent": 5.0}],
            "losers": [{"symbol": "BBB.NS", "change_percent": -4.0}],
        }
    )

    valid = "The market had 3 advancers and 1 decliner; AAA.NS gained 5%."
    assert validate_grounded_narrative(valid, prompt).valid

    hallucinated = "The market had 8 advancers and 1 decliner."
    result = validate_grounded_narrative(hallucinated, prompt)
    assert not result.valid
    assert "unsupported numeric claim" in result.reason


def test_recommendation_requires_confidence_evidence_and_risk_anchors() -> None:
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
    prompt, _fallback = recommendation_explanation(rec)

    valid = (
        "Watch AAA.NS with 70% confidence because RSI at 60 shows bullish "
        "momentum. Standard market risk applies."
    )
    assert validate_grounded_narrative(valid, prompt).valid

    for invalid, reason in (
        ("Watch AAA.NS because RSI at 60 is bullish. Standard market risk applies.",
         "confidence"),
        ("Watch AAA.NS with 70% confidence. Standard market risk applies.",
         "evidence"),
        ("Watch AAA.NS with 70% confidence because RSI at 60 is bullish.",
         "risks"),
    ):
        result = validate_grounded_narrative(invalid, prompt)
        assert not result.valid
        assert reason in result.reason


def test_exact_price_prediction_is_rejected_even_if_number_is_supplied() -> None:
    prompt, _fallback = market_section(
        {
            "breadth": {
                "advancers": 1,
                "decliners": 1,
                "unchanged": 0,
                "total": 2,
                "advance_decline_ratio": 1.0,
            },
            "gainers": [{"symbol": "AAA.NS", "change_percent": 5.0}],
            "losers": [{"symbol": "BBB.NS", "change_percent": -5.0}],
        }
    )
    result = validate_grounded_narrative(
        "AAA.NS will rise 5% after 1 advancer and 1 decliner.", prompt
    )
    assert not result.valid
    assert "prediction" in result.reason
