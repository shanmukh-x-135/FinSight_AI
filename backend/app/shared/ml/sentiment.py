"""Sentiment scoring — provider-agnostic, with FinBERT and a lexicon fallback.

Sentiment is a *deterministic classification input* to the feature vector
("analytics before AI" — the LLM never scores sentiment). Two backends behind
one interface:

* **FinBertProsus** — the design doc's model (ProsusAI/finbert via
  transformers/torch). Lazy-loaded; batched. Requires the ML extras
  (`requirements-ml.txt`).
* **LexiconScorer** — a dependency-free financial-sentiment lexicon. The default
  and the automatic fallback when the ML stack isn't available, so the pipeline
  always works (light image, no model download, fast/deterministic tests).

Both emit a compound score in [-1, 1] plus per-class proportions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)


@dataclass(frozen=True)
class SentimentScore:
    label: str          # "positive" | "negative" | "neutral"
    score: float        # compound in [-1, 1] (positive - negative)
    positive: float
    negative: float
    neutral: float


class SentimentScorer(Protocol):
    def score(self, texts: list[str]) -> list[SentimentScore]:
        """Score a batch of texts (batched for efficiency)."""
        ...


# --------------------------------------------------------------------------- #
# Lexicon backend                                                             #
# --------------------------------------------------------------------------- #
_POSITIVE_WORDS = frozenset(
    """surge surges surged gain gains gained rally rallies rallied profit profits
    profitable beat beats growth grew jump jumps jumped rise rises rose soar soars
    soared upgrade upgraded bullish record high higher strong stronger boost boosts
    boosted outperform outperforms positive robust expansion dividend buy optimism
    optimistic recovery recover recovers wins win top best exceeds exceeded rebound
    rebounds rebounded upbeat gains uptrend""".split()
)
_NEGATIVE_WORDS = frozenset(
    """fall falls fell drop drops dropped plunge plunges plunged loss losses
    declined decline declines slump slumps slumped weak weaker miss misses missed
    cut cuts downgrade downgraded bearish crash crashed low lower concern concerns
    fear fears risk risks slowdown layoff layoffs fraud probe sell selloff pessimism
    worst plummet plummets plummeted tumble tumbles tumbled warn warns warning
    default defaults weakness downturn losses slid slide""".split()
)
_WORD_RE = re.compile(r"[a-z]+")
_NEUTRAL_BAND = 0.1


class LexiconScorer:
    """Deterministic financial-sentiment lexicon scorer."""

    def _score_one(self, text: str) -> SentimentScore:
        tokens = _WORD_RE.findall((text or "").lower())
        pos = sum(1 for t in tokens if t in _POSITIVE_WORDS)
        neg = sum(1 for t in tokens if t in _NEGATIVE_WORDS)
        total = pos + neg
        if total == 0:
            return SentimentScore("neutral", 0.0, 0.0, 0.0, 1.0)
        compound = (pos - neg) / total
        p, n = pos / total, neg / total
        if compound > _NEUTRAL_BAND:
            label = "positive"
        elif compound < -_NEUTRAL_BAND:
            label = "negative"
        else:
            label = "neutral"
        return SentimentScore(label, compound, p, n, max(0.0, 1.0 - p - n))

    def score(self, texts: list[str]) -> list[SentimentScore]:
        return [self._score_one(t) for t in texts]


# --------------------------------------------------------------------------- #
# FinBERT backend (design doc's model)                                        #
# --------------------------------------------------------------------------- #
class FinBertProsus:
    """ProsusAI/finbert via transformers. Lazy-loaded; batched inference."""

    MODEL = "ProsusAI/finbert"

    def __init__(self) -> None:
        # Import here so the module (and tests) don't require torch/transformers.
        from transformers import pipeline  # noqa: PLC0415

        self._pipe = pipeline("text-classification", model=self.MODEL, top_k=None)

    def score(self, texts: list[str]) -> list[SentimentScore]:
        if not texts:
            return []
        results = self._pipe(texts, batch_size=16, truncation=True)
        out: list[SentimentScore] = []
        for row in results:
            probs = {r["label"].lower(): float(r["score"]) for r in row}
            pos = probs.get("positive", 0.0)
            neg = probs.get("negative", 0.0)
            neu = probs.get("neutral", 0.0)
            label = max(("positive", "negative", "neutral"), key=lambda k: probs.get(k, 0.0))
            out.append(SentimentScore(label, pos - neg, pos, neg, neu))
        return out


# --------------------------------------------------------------------------- #
# Factory                                                                     #
# --------------------------------------------------------------------------- #
_scorer: SentimentScorer | None = None


def get_sentiment_scorer(backend: str | None = None) -> SentimentScorer:
    """Return a cached scorer. FinBERT if requested+available, else lexicon."""
    global _scorer
    if _scorer is not None and backend is None:
        return _scorer

    chosen = (backend or settings.sentiment_backend).lower()
    if chosen == "finbert":
        try:
            scorer: SentimentScorer = FinBertProsus()
            logger.info("sentiment_backend_loaded", extra={"backend": "finbert"})
        except Exception as exc:  # noqa: BLE001 — ML stack/model may be missing
            logger.warning(
                "finbert_unavailable_fallback_lexicon",
                extra={"error": type(exc).__name__},
            )
            scorer = LexiconScorer()
    else:
        scorer = LexiconScorer()

    if backend is None:
        _scorer = scorer
    return scorer
