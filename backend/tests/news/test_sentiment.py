"""Unit tests for the lexicon sentiment scorer (the default backend)."""

from __future__ import annotations

import sys
from types import ModuleType

import pytest

from app.shared.ml.sentiment import FinBertProsus, LexiconScorer, get_sentiment_scorer

POSITIVE = "Company profits surge as revenue beats estimates and shares rally to a record high"
NEGATIVE = "Shares plunge after the firm reports a massive loss and slashes its dividend"
NEUTRAL = "The company held its annual general meeting on Tuesday afternoon"


def test_positive_text_scores_positive() -> None:
    s = LexiconScorer().score([POSITIVE])[0]
    assert s.label == "positive"
    assert s.score > 0


def test_negative_text_scores_negative() -> None:
    s = LexiconScorer().score([NEGATIVE])[0]
    assert s.label == "negative"
    assert s.score < 0


def test_neutral_text_scores_neutral() -> None:
    s = LexiconScorer().score([NEUTRAL])[0]
    assert s.label == "neutral"
    assert s.score == 0.0


def test_scores_are_bounded() -> None:
    for text in (POSITIVE, NEGATIVE, NEUTRAL):
        s = LexiconScorer().score([text])[0]
        assert -1.0 <= s.score <= 1.0


def test_batch_and_empty() -> None:
    scorer = LexiconScorer()
    assert len(scorer.score([POSITIVE, NEGATIVE, NEUTRAL])) == 3
    assert scorer.score([]) == []


def test_default_scorer_is_lexicon() -> None:
    assert isinstance(get_sentiment_scorer(), LexiconScorer)


def test_finbert_request_falls_back_to_lexicon_when_unavailable(monkeypatch) -> None:
    from app.shared.ml import sentiment as mod

    def _raise() -> None:
        raise RuntimeError("transformers/torch not installed")

    monkeypatch.setattr(mod, "FinBertProsus", _raise)
    # Requesting finbert with the ML stack unavailable must degrade gracefully.
    assert isinstance(mod.get_sentiment_scorer("finbert"), LexiconScorer)


def test_finbert_successful_batched_inference_contract(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class _Pipeline:
        def __call__(self, texts, **kwargs):
            calls["texts"] = texts
            calls["inference_kwargs"] = kwargs
            return [
                [
                    {"label": "positive", "score": 0.8},
                    {"label": "neutral", "score": 0.15},
                    {"label": "negative", "score": 0.05},
                ],
                [
                    {"label": "NEGATIVE", "score": 0.7},
                    {"label": "NEUTRAL", "score": 0.2},
                    {"label": "POSITIVE", "score": 0.1},
                ],
            ]

    def pipeline(task, **kwargs):
        calls["task"] = task
        calls["factory_kwargs"] = kwargs
        return _Pipeline()

    transformers = ModuleType("transformers")
    transformers.pipeline = pipeline  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "transformers", transformers)

    scorer = get_sentiment_scorer("finbert")
    assert isinstance(scorer, FinBertProsus)
    scores = scorer.score([POSITIVE, NEGATIVE])

    assert calls["task"] == "text-classification"
    assert calls["factory_kwargs"] == {
        "model": FinBertProsus.MODEL,
        "top_k": None,
    }
    assert calls["inference_kwargs"] == {"batch_size": 16, "truncation": True}
    assert scores[0].label == "positive"
    assert scores[0].score == pytest.approx(0.75)
    assert scores[1].label == "negative"
    assert scores[1].score == pytest.approx(-0.6)
    assert scorer.score([]) == []
