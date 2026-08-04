"""Explainability validation (design doc §5.8).

Every recommendation must carry evidence, a confidence, and risks; every report
section must have a non-empty narrative. This guard runs before a report is
persisted — the roadmap's non-optional "reject anything missing evidence/
confidence/risks". Since those fields are computed deterministically, well-formed
output passes by construction; the guard catches regressions and any empty LLM
prose.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import status

from app.shared.exceptions import AppException


class ExplainabilityError(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_type = "explainability_validation_failed"


@dataclass(frozen=True)
class GroundingResult:
    valid: bool
    reason: str = ""


_FACTS_MARKER = "Facts (JSON):\n"
_NUMBER_RE = re.compile(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?%?")
_PREDICTION_RE = re.compile(
    r"\b(?:will|may|might|could|guaranteed to|certain to|expected to|projected to)\s+"
    r"(?:rise|fall|gain|drop|reach|hit|trade|close)\b|"
    r"\b(?:price target|target price|buy now|sell now|buy at|sell at)\b|"
    r"\b(?:recommend|should|must)\s+(?:buy|sell)\b",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[a-z][a-z0-9-]{2,}")
_STOP_WORDS = {
    "and", "are", "for", "from", "has", "its", "the", "this", "that",
    "with", "applies", "risk", "risks", "market", "price", "today",
}


def _facts_from_prompt(prompt: str) -> dict[str, Any] | None:
    if _FACTS_MARKER not in prompt:
        return None
    try:
        facts = json.loads(prompt.split(_FACTS_MARKER, 1)[1])
    except (json.JSONDecodeError, TypeError):
        return None
    return facts if isinstance(facts, dict) else None


def _numbers(value: Any) -> list[Decimal]:
    found: list[Decimal] = []
    if isinstance(value, bool) or value is None:
        return found
    if isinstance(value, (int, float, Decimal)):
        try:
            found.append(Decimal(str(value)))
        except InvalidOperation:
            pass
        return found
    if isinstance(value, str):
        for token in _NUMBER_RE.findall(value):
            try:
                found.append(Decimal(token.rstrip("%").replace(",", "")))
            except InvalidOperation:
                continue
        return found
    if isinstance(value, dict):
        for item in value.values():
            found.extend(_numbers(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(_numbers(item))
    return found


def _number_is_supported(token: str, facts: dict[str, Any]) -> bool:
    try:
        claim = Decimal(token.rstrip("%").replace(",", ""))
    except InvalidOperation:
        return False
    decimals = len(token.rstrip("%").partition(".")[2])
    for source in _numbers(facts):
        candidates = [source]
        if token.endswith("%") and -1 <= source <= 1:
            candidates.append(source * 100)
        if any(round(candidate, decimals) == claim for candidate in candidates):
            return True
    return False


def _mentions_number(text: str, expected: int | float) -> bool:
    target = Decimal(str(expected))
    for token in _NUMBER_RE.findall(text):
        try:
            value = Decimal(token.rstrip("%").replace(",", ""))
        except InvalidOperation:
            continue
        decimals = len(token.rstrip("%").partition(".")[2])
        if round(target, decimals) == value:
            return True
        if token.endswith("%") and -1 <= target <= 1:
            if round(target * 100, decimals) == value:
                return True
    return False


def _meaningful_words(values: list[str]) -> set[str]:
    return {
        word
        for value in values
        for word in _WORD_RE.findall(value.lower())
        if word not in _STOP_WORDS
    }


def _mentions_source_anchor(text: str, values: list[str]) -> bool:
    words = _meaningful_words(values)
    if words.intersection(_WORD_RE.findall(text.lower())):
        return True
    return any(_mentions_number(text, value) for value in _numbers(values))


def validate_grounded_narrative(text: str, prompt: str) -> GroundingResult:
    """Check model prose against the structured facts embedded in its prompt.

    This deliberately uses deterministic, explainable checks rather than a
    second model: unsupported numbers and exact-price predictions are rejected,
    then each section must cite the anchors that make its claims auditable.
    """
    narrative = text.strip()
    if not narrative:
        return GroundingResult(False, "empty response")
    facts = _facts_from_prompt(prompt)
    if facts is None:
        return GroundingResult(False, "missing or malformed prompt facts")
    if _PREDICTION_RE.search(narrative):
        return GroundingResult(False, "contains an exact-price prediction or advice")
    for token in _NUMBER_RE.findall(narrative):
        if not _number_is_supported(token, facts):
            return GroundingResult(False, f"unsupported numeric claim: {token}")

    lower = narrative.lower()
    if {"symbol", "confidence", "evidence", "risks"} <= facts.keys():
        symbol = str(facts["symbol"])
        if symbol.lower() not in lower:
            return GroundingResult(False, "recommendation omits its symbol")
        if not _mentions_number(narrative, facts["confidence"]):
            return GroundingResult(False, "recommendation omits its confidence")
        evidence = [str(v) for v in facts["evidence"]]
        if not _mentions_source_anchor(narrative, evidence):
            return GroundingResult(False, "recommendation omits supplied evidence")
        risks = [str(v) for v in facts["risks"]]
        if not _mentions_source_anchor(narrative, risks):
            return GroundingResult(False, "recommendation omits supplied risks")
    elif "breadth" in facts:
        breadth = facts["breadth"]
        if not _mentions_number(narrative, breadth["advancers"]):
            return GroundingResult(False, "market summary omits advancers")
        if not _mentions_number(narrative, breadth["decliners"]):
            return GroundingResult(False, "market summary omits decliners")
        if not any(word in lower for word in ("advance", "gainer", "rose")):
            return GroundingResult(False, "market summary lacks advancing context")
        if not any(word in lower for word in ("decline", "loser", "fell")):
            return GroundingResult(False, "market summary lacks declining context")
    elif "statistics" in facts and "similar_sessions" in facts:
        sample_size = facts["statistics"].get("sample_size", 0)
        if sample_size and not _mentions_number(narrative, sample_size):
            return GroundingResult(False, "historical summary omits sample size")
        if not any(word in lower for word in ("historical", "past", "similar")):
            return GroundingResult(False, "historical summary lacks historical framing")
        if sample_size and not any(
            word in lower for word in ("probability", "scenario", "context", "forecast")
        ):
            return GroundingResult(False, "historical summary omits uncertainty")
    elif facts.get("valuation_complete") is False:
        if "portfolio" not in lower:
            return GroundingResult(False, "portfolio summary omits portfolio context")
        if not any(word in lower for word in ("missing", "unavailable", "withheld")):
            return GroundingResult(False, "portfolio summary hides incomplete valuation")
    elif "total_value" in facts and "health_score" in facts:
        if "portfolio" not in lower:
            return GroundingResult(False, "portfolio summary omits portfolio context")
        if str(facts["risk_level"]).lower() not in lower:
            return GroundingResult(False, "portfolio summary omits risk level")
        if not _mentions_number(narrative, facts["health_score"]):
            return GroundingResult(False, "portfolio summary omits health score")
    elif "source_narratives" in facts:
        source_words = _meaningful_words(list(facts["source_narratives"].values()))
        watchlist = [str(v).lower() for v in facts.get("watchlist", [])]
        if not source_words.intersection(_WORD_RE.findall(lower)) and not any(
            symbol in lower for symbol in watchlist
        ):
            return GroundingResult(False, "executive summary lacks a supplied anchor")

    return GroundingResult(True)


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
