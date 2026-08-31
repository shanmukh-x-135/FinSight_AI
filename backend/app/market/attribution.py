"""Pure deterministic helpers for stock movement attribution.

Outputs describe associations in available data, never causal certainty.
"""

from __future__ import annotations

from collections import Counter

from app.market.schemas import ConflictSignalOut, EvidenceConflictOut


def directional_view(value: float | None, *, band: float) -> str:
    if value is None:
        return "unavailable"
    if value > band:
        return "bullish"
    if value < -band:
        return "bearish"
    return "neutral"


def technical_view(
    close: float | None,
    ema_20: float | None,
    macd_histogram: float | None,
) -> tuple[str, str, float]:
    observations: list[str] = []
    votes: list[str] = []
    if close is not None and ema_20 is not None:
        above = close >= ema_20
        votes.append("bullish" if above else "bearish")
        observations.append(f"Price is {'above' if above else 'below'} EMA20")
    if macd_histogram is not None:
        positive = macd_histogram >= 0
        votes.append("bullish" if positive else "bearish")
        observations.append(f"MACD histogram is {'positive' if positive else 'negative'}")
    if not votes:
        return "unavailable", "Technical indicators unavailable", 0.0
    counts = Counter(votes)
    if len(counts) > 1:
        return "neutral", "; ".join(observations), 0.5
    return votes[0], "; ".join(observations), 0.72


def conflict_summary(signals: list[ConflictSignalOut]) -> EvidenceConflictOut:
    available = [signal for signal in signals if signal.direction != "unavailable"]
    directional = [
        signal for signal in available if signal.direction in {"bullish", "bearish"}
    ]
    if not available:
        return EvidenceConflictOut(
            consensus="unavailable", confidence=0.0, conflict_detected=False, signals=signals
        )
    votes = Counter(signal.direction for signal in directional)
    conflict = votes["bullish"] > 0 and votes["bearish"] > 0
    if conflict or not directional:
        consensus = "mixed" if conflict else "neutral"
    else:
        consensus = directional[0].direction
    agreement = (
        max(votes.values()) / len(directional) if directional else 0.5
    )
    base_confidence = sum(signal.confidence for signal in available) / len(available)
    return EvidenceConflictOut(
        consensus=consensus,
        confidence=round(base_confidence * agreement, 4),
        conflict_detected=conflict,
        signals=signals,
    )
