"""Tests for explainability validation (evidence/confidence/risks/narrative)."""

from __future__ import annotations

import pytest

from app.intelligence.explainability import (
    ExplainabilityError,
    validate_recommendation,
    validate_report,
)


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
