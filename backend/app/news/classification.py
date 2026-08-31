"""Deterministic article enrichment for evidence-backed news intelligence.

The classifier intentionally uses a small, inspectable taxonomy.  It does not
claim that a keyword proves an event; it records which reviewed rule produced
the category and leaves unmatched coverage explicitly unclassified.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class EventClassification:
    category: str
    driver: str
    confidence: float


_EVENT_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Earnings", "Reported financial performance", ("earnings", "profit", "loss", "revenue", "quarterly result", "results")),
    ("Guidance", "Management outlook or guidance", ("guidance", "outlook", "forecast", "expects", "target")),
    ("M&A", "Merger, acquisition, or divestment activity", ("acquisition", "acquires", "merger", "takeover", "divest")),
    ("Regulation", "Regulatory or policy development", ("regulator", "regulation", "policy", "sebi", "rbi", "government approval")),
    ("Order Win", "New order or contract announcement", ("order win", "wins order", "contract awarded", "new contract")),
    ("Product Launch", "Product or service announcement", ("product launch", "launches", "unveils", "new product")),
    ("Management", "Management or leadership development", ("ceo", "cfo", "chairman", "management", "resigns", "appoints")),
    ("Brokerage Action", "Brokerage rating or target action", ("brokerage", "upgrade", "downgrade", "price target", "target price", "rating")),
    ("Macro", "Macroeconomic or market-wide development", ("inflation", "interest rate", "gdp", "rupee", "currency", "economy", "macro")),
    ("Commodity Exposure", "Commodity-price or input-cost development", ("crude", "oil price", "commodity", "gold price", "metal price", "refining margin")),
    ("Litigation", "Legal dispute or investigation", ("lawsuit", "litigation", "court", "probe", "investigation", "legal")),
    ("Corporate Action", "Corporate action announcement", ("dividend", "buyback", "stock split", "bonus issue", "rights issue")),
)

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def classify_event(title: str, summary: str) -> EventClassification:
    text = f"{title} {summary}".lower()
    for category, driver, phrases in _EVENT_RULES:
        matched = [phrase for phrase in phrases if phrase in text]
        if matched:
            # Multiple independent phrase matches make the rule more specific,
            # but keyword classification is deliberately capped below certainty.
            confidence = min(0.9, 0.62 + 0.08 * (len(matched) - 1))
            return EventClassification(category, driver, confidence)
    return EventClassification("Other", "Unclassified company coverage", 0.35)


def evidence_excerpt(title: str, summary: str, *, limit: int = 320) -> str:
    """Return a safe, bounded excerpt traceable to provider-supplied text."""
    raw = summary.strip() or title.strip()
    clean = _SPACE_RE.sub(" ", _TAG_RE.sub(" ", html.unescape(raw))).strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def sentiment_confidence(
    *, score: float, positive: float, negative: float, neutral: float
) -> float:
    """Confidence in the stored class, without turning neutral into certainty."""
    class_probability = max(positive, negative, neutral)
    if abs(score) < 0.1:
        return round(min(class_probability, 0.6), 4)
    return round(min(0.99, max(0.5, class_probability)), 4)
