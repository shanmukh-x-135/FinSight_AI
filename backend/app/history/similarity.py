"""Similarity scoring and historical-outcome statistics — pure functions.

Statistics are computed from the *actual* next-day returns of retrieved
neighbour sessions (design doc §5.6): the LLM later explains them; it never
computes them.
"""

from __future__ import annotations

import math
import statistics as stats


def distance_to_similarity(distance: float) -> float:
    """Map a non-negative L2 distance to a (0, 1] similarity (monotonic)."""
    return 1.0 / (1.0 + max(distance, 0.0))


def outcome_label(next_day_return: float | None) -> str | None:
    if next_day_return is None:
        return None
    if next_day_return > 0:
        return "bullish"
    if next_day_return < 0:
        return "bearish"
    return "neutral"


def compute_statistics(next_day_returns: list[float | None], k: int) -> dict:
    """Summarize the next-day outcomes of neighbour sessions.

    Only neighbours with a known outcome (non-None) count toward the sample.
    Returns bullish/bearish/neutral counts, bullish probability, return
    distribution stats, best/worst case, and a 95% CI of the mean return.
    """
    known = [r for r in next_day_returns if r is not None]
    n = len(known)
    empty = {
        "k": k,
        "sample_size": 0,
        "bullish_count": 0,
        "bearish_count": 0,
        "neutral_count": 0,
        "bullish_probability": None,
        "avg_next_day_return": None,
        "median_next_day_return": None,
        "std_next_day_return": None,
        "best_case_return": None,
        "worst_case_return": None,
        "ci_low": None,
        "ci_high": None,
    }
    if n == 0:
        return empty

    bullish = sum(1 for r in known if r > 0)
    bearish = sum(1 for r in known if r < 0)
    neutral = n - bullish - bearish

    mean = stats.fmean(known)
    std = stats.stdev(known) if n >= 2 else 0.0
    if n >= 2:
        margin = 1.96 * std / math.sqrt(n)
        ci_low, ci_high = mean - margin, mean + margin
    else:
        ci_low = ci_high = mean

    return {
        "k": k,
        "sample_size": n,
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
        "bullish_probability": bullish / n,
        "avg_next_day_return": mean,
        "median_next_day_return": stats.median(known),
        "std_next_day_return": std,
        "best_case_return": max(known),
        "worst_case_return": min(known),
        "ci_low": ci_low,
        "ci_high": ci_high,
    }
