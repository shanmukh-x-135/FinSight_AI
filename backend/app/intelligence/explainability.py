"""Explainability validation (design doc §5.8).

Every recommendation must carry evidence, a confidence, and risks; every report
section must have a non-empty narrative. This guard runs before a report is
persisted — the roadmap's non-optional "reject anything missing evidence/
confidence/risks". Since those fields are computed deterministically, well-formed
output passes by construction; the guard catches regressions and any empty LLM
prose.
"""

from __future__ import annotations

from fastapi import status

from app.shared.exceptions import AppException


class ExplainabilityError(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_type = "explainability_validation_failed"


def validate_recommendation(rec: dict) -> None:
    if not rec.get("evidence"):
        raise ExplainabilityError(f"Recommendation for {rec.get('symbol')} has no evidence.")
    if rec.get("confidence") is None:
        raise ExplainabilityError(f"Recommendation for {rec.get('symbol')} has no confidence.")
    if not rec.get("risks"):
        raise ExplainabilityError(f"Recommendation for {rec.get('symbol')} has no risks.")
    if not (rec.get("explanation") or "").strip():
        raise ExplainabilityError(f"Recommendation for {rec.get('symbol')} has no explanation.")


def validate_report(sections: dict) -> None:
    if not sections.get("market_summary", {}).get("narrative", "").strip():
        raise ExplainabilityError("Report is missing a market summary.")
    if "recommendations" not in sections:
        raise ExplainabilityError("Report is missing recommendations.")
    for rec in sections["recommendations"]:
        validate_recommendation(rec)
    if not (sections.get("executive_summary") or "").strip():
        raise ExplainabilityError("Report is missing an executive summary.")
