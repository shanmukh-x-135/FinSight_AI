"""Unit tests for similarity scoring and outcome statistics (hand-verified)."""

from __future__ import annotations

import math

import pytest

from app.history.similarity import (
    compute_statistics,
    distance_to_similarity,
    outcome_label,
)


def test_distance_to_similarity_monotonic() -> None:
    assert distance_to_similarity(0.0) == pytest.approx(1.0)
    assert distance_to_similarity(1.0) == pytest.approx(0.5)
    assert distance_to_similarity(3.0) == pytest.approx(0.25)
    assert distance_to_similarity(0.0) > distance_to_similarity(5.0)


def test_outcome_label() -> None:
    assert outcome_label(0.01) == "bullish"
    assert outcome_label(-0.01) == "bearish"
    assert outcome_label(0.0) == "neutral"
    assert outcome_label(None) is None


def test_compute_statistics_reference() -> None:
    # known returns: 0.02, -0.01, 0.03, -0.02 (one None ignored)
    s = compute_statistics([0.02, -0.01, 0.03, None, -0.02], k=5)
    assert s["sample_size"] == 4
    assert s["bullish_count"] == 2
    assert s["bearish_count"] == 2
    assert s["neutral_count"] == 0
    assert s["bullish_probability"] == pytest.approx(0.5)
    assert s["avg_next_day_return"] == pytest.approx(0.005)
    assert s["median_next_day_return"] == pytest.approx(0.005)
    assert s["best_case_return"] == pytest.approx(0.03)
    assert s["worst_case_return"] == pytest.approx(-0.02)

    std = s["std_next_day_return"]
    assert std == pytest.approx(0.0238048, abs=1e-6)
    margin = 1.96 * std / math.sqrt(4)
    assert s["ci_low"] == pytest.approx(0.005 - margin)
    assert s["ci_high"] == pytest.approx(0.005 + margin)


def test_compute_statistics_empty_sample() -> None:
    s = compute_statistics([None, None], k=3)
    assert s["sample_size"] == 0
    assert s["bullish_probability"] is None
    assert s["avg_next_day_return"] is None
    assert s["ci_low"] is None


def test_compute_statistics_single_known_has_zero_std() -> None:
    s = compute_statistics([0.05, None], k=2)
    assert s["sample_size"] == 1
    assert s["std_next_day_return"] == pytest.approx(0.0)
    assert s["ci_low"] == pytest.approx(0.05)  # CI collapses to the point
    assert s["ci_high"] == pytest.approx(0.05)
