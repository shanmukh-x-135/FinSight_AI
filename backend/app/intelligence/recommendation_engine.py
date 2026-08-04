"""Recommendation engine — deterministic filtering, ranking, evidence, risks.

The LLM NEVER touches this. Candidate scoring, ranking order, confidence,
evidence, and risks are all computed from the analytics (Phases 2–5). The LLM
later only writes prose around this structured output. Ranking is stable
(score desc, then symbol) so identical inputs always yield the identical order —
the phase's key correctness property.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.intelligence import constants as C


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass(frozen=True)
class CandidateInput:
    """Precomputed, structured facts for one stock (from market/news/history)."""

    symbol: str
    name: str | None
    sector: str | None
    price: float
    change_percent: float | None
    rsi: float | None
    ema20_distance_pct: float | None   # (price - ema20) / ema20 * 100
    ema50_distance_pct: float | None
    macd_hist: float | None
    atr_pct: float | None              # atr / price * 100
    sentiment: float | None            # [-1, 1] or None
    sector_change_percent: float | None
    # Market-wide historical analog stats (same for all candidates in a run).
    hist_bullish_probability: float | None = None
    hist_sample_size: int | None = None


@dataclass
class Recommendation:
    symbol: str
    name: str | None
    sector: str | None
    action: str                 # "watch" | "avoid" | "hold"
    score: float
    confidence: int             # 0–100
    evidence: list[str]
    risks: list[str]
    historical_context: dict = field(default_factory=dict)
    explanation: str = ""       # filled by the narrator/LLM later


def _score(c: CandidateInput) -> float:
    rsi_comp = _clamp(((c.rsi or 50) - 50) / 50, -1, 1)
    trend_comp = _clamp((c.ema20_distance_pct or 0) / 5, -1, 1)
    macd_comp = 0.5 if (c.macd_hist or 0) > 0 else (-0.5 if (c.macd_hist or 0) < 0 else 0.0)
    technical = (rsi_comp + trend_comp + macd_comp) / 3

    momentum = _clamp((c.change_percent or 0) / 3, -1, 1)
    sector = _clamp((c.sector_change_percent or 0) / 3, -1, 1)
    sentiment = _clamp(c.sentiment or 0, -1, 1)
    historical = (
        _clamp((c.hist_bullish_probability - 0.5) * 2, -1, 1)
        if c.hist_bullish_probability is not None
        else 0.0
    )
    vol_penalty = _clamp((c.atr_pct or 0) / 5, 0, 1)

    return (
        C.W_TECHNICAL * technical
        + C.W_MOMENTUM * momentum
        + C.W_SECTOR * sector
        + C.W_SENTIMENT * sentiment
        + C.W_HISTORICAL * historical
        - C.W_VOLATILITY_PENALTY * vol_penalty
    )


def _action(score: float) -> str:
    if score >= C.WATCH_THRESHOLD:
        return "watch"
    if score <= C.AVOID_THRESHOLD:
        return "avoid"
    return "hold"


def _confidence(score: float, c: CandidateInput) -> int:
    hist_adj = (
        (c.hist_bullish_probability - 0.5) * 20
        if c.hist_bullish_probability is not None
        else 0.0
    )
    return int(round(_clamp(50 + score * 40 + hist_adj, 5, 95)))


def _evidence(c: CandidateInput) -> list[str]:
    ev: list[str] = []
    if c.rsi is not None:
        tag = (
            "bullish momentum" if c.rsi >= C.RSI_BULLISH
            else "oversold" if c.rsi <= C.RSI_OVERSOLD
            else "neutral"
        )
        ev.append(f"RSI at {c.rsi:.0f} ({tag})")
    if c.ema20_distance_pct is not None:
        if c.ema20_distance_pct > 0:
            position = "above"
        elif c.ema20_distance_pct < 0:
            position = "below"
        else:
            position = "at"
        ev.append(
            f"Price {position} its 20-day EMA "
            f"({c.ema20_distance_pct:+.1f}%)"
        )
    if c.macd_hist is not None:
        if c.macd_hist > 0:
            direction = "positive"
        elif c.macd_hist < 0:
            direction = "negative"
        else:
            direction = "neutral"
        ev.append(f"MACD histogram {direction}")
    if c.change_percent is not None:
        ev.append(f"{c.change_percent:+.1f}% today")
    if c.sector and c.sector_change_percent is not None:
        ev.append(f"{c.sector} sector {c.sector_change_percent:+.1f}% today")
    if c.sentiment is not None and c.sentiment != 0:
        lbl = "positive" if c.sentiment > 0 else "negative"
        ev.append(f"News sentiment {lbl} ({c.sentiment:+.2f})")
    if c.hist_bullish_probability is not None and c.hist_sample_size:
        pct = round(c.hist_bullish_probability * 100)
        ev.append(
            f"{pct}% of {c.hist_sample_size} similar historical sessions closed higher"
        )
    return ev


def _risks(c: CandidateInput) -> list[str]:
    risks: list[str] = []
    if c.rsi is not None and c.rsi >= C.RSI_OVERBOUGHT:
        risks.append(f"Overbought (RSI {c.rsi:.0f})")
    if c.atr_pct is not None and c.atr_pct >= C.HIGH_VOLATILITY_PCT:
        risks.append(f"Elevated volatility (ATR {c.atr_pct:.1f}%)")
    if c.sentiment is not None and c.sentiment < 0:
        risks.append("Negative news sentiment")
    if c.ema50_distance_pct is not None and c.ema50_distance_pct < 0:
        risks.append("Trading below its 50-day trend")
    if c.hist_bullish_probability is not None and c.hist_bullish_probability < 0.5:
        risks.append("Similar historical sessions favored downside")
    if not risks:
        risks.append("Standard market risk applies")
    return risks


def build_recommendation(c: CandidateInput) -> Recommendation:
    score = _score(c)
    return Recommendation(
        symbol=c.symbol,
        name=c.name,
        sector=c.sector,
        action=_action(score),
        score=round(score, 6),
        confidence=_confidence(score, c),
        evidence=_evidence(c),
        risks=_risks(c),
        historical_context={
            "bullish_probability": c.hist_bullish_probability,
            "sample_size": c.hist_sample_size,
        },
    )


def rank_candidates(candidates: list[CandidateInput]) -> list[Recommendation]:
    """Return all candidates as recommendations, deterministically ranked.

    Order: score descending, then symbol ascending (stable tie-break) — so the
    same inputs always produce the same order.
    """
    recs = [build_recommendation(c) for c in candidates]
    recs.sort(key=lambda r: (-r.score, r.symbol))
    return recs


def select_watchlist(recs: list[Recommendation], top_n: int) -> list[Recommendation]:
    """Top-N 'watch' recommendations (positive score), in ranked order."""
    return [r for r in recs if r.action == "watch"][:top_n]


def select_risk_alerts(recs: list[Recommendation]) -> list[Recommendation]:
    """'avoid' recommendations (negative score), most-negative first."""
    return [r for r in recs if r.action == "avoid"][::-1]
