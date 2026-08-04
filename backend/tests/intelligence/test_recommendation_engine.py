"""Unit tests for the deterministic recommendation engine."""

from __future__ import annotations

from app.intelligence.recommendation_engine import (
    CandidateInput,
    build_recommendation,
    rank_candidates,
    select_risk_alerts,
    select_watchlist,
)


def _candidate(symbol: str, **kw) -> CandidateInput:
    base = dict(
        symbol=symbol, name=symbol, sector="Tech", price=100.0, change_percent=0.0,
        rsi=50.0, ema20_distance_pct=0.0, ema50_distance_pct=0.0, macd_hist=0.0,
        atr_pct=1.0, sentiment=0.0, sector_change_percent=0.0,
        hist_bullish_probability=None, hist_sample_size=None,
    )
    base.update(kw)
    return CandidateInput(**base)


def test_ranking_is_deterministic_and_stable() -> None:
    cands = [
        _candidate("AAA", rsi=65, change_percent=2, ema20_distance_pct=3, macd_hist=1, sentiment=0.5),
        _candidate("BBB", rsi=40, change_percent=-2, ema20_distance_pct=-3, macd_hist=-1, sentiment=-0.5),
        _candidate("CCC", rsi=50),
    ]
    first = [r.symbol for r in rank_candidates(cands)]
    second = [r.symbol for r in rank_candidates(list(reversed(cands)))]
    # Same inputs → same order regardless of input order.
    assert first == second
    # The strongly-bullish candidate ranks first, bearish last.
    assert first[0] == "AAA"
    assert first[-1] == "BBB"


def test_tie_break_is_alphabetical_by_symbol() -> None:
    # Two identical candidates (same score) → ordered by symbol.
    cands = [_candidate("ZZZ"), _candidate("AAA")]
    assert [r.symbol for r in rank_candidates(cands)] == ["AAA", "ZZZ"]


def test_actions_reflect_score_sign() -> None:
    bullish = build_recommendation(
        _candidate("AAA", rsi=68, change_percent=3, ema20_distance_pct=4,
                   macd_hist=2, sentiment=0.6, sector_change_percent=2)
    )
    bearish = build_recommendation(
        _candidate("BBB", rsi=35, change_percent=-3, ema20_distance_pct=-4,
                   macd_hist=-2, sentiment=-0.6, sector_change_percent=-2)
    )
    assert bullish.action == "watch"
    assert bearish.action == "avoid"
    assert 5 <= bullish.confidence <= 95
    assert bullish.confidence > bearish.confidence


def test_evidence_and_risks_content() -> None:
    rec = build_recommendation(
        _candidate("AAA", rsi=75, ema20_distance_pct=2.5, macd_hist=1.0,
                   change_percent=1.5, sentiment=-0.3, atr_pct=4.0,
                   ema50_distance_pct=-1.0, hist_bullish_probability=0.6, hist_sample_size=10)
    )
    ev = " | ".join(rec.evidence)
    assert "RSI at 75" in ev
    assert "20-day EMA" in ev
    assert "MACD histogram positive" in ev
    assert "60% of 10 similar historical sessions closed higher" in ev
    # Risks: overbought, high volatility, negative sentiment, below 50-day.
    risks = " | ".join(rec.risks)
    assert "Overbought (RSI 75)" in risks
    assert "Elevated volatility" in risks
    assert "Negative news sentiment" in risks
    assert "below its 50-day trend" in risks.lower()


def test_no_risks_yields_standard_risk_note() -> None:
    rec = build_recommendation(
        _candidate("AAA", rsi=55, atr_pct=1.0, sentiment=0.2,
                   ema50_distance_pct=1.0, hist_bullish_probability=0.6)
    )
    assert rec.risks == ["Standard market risk applies"]


def test_select_watchlist_and_alerts() -> None:
    recs = rank_candidates([
        _candidate("AAA", rsi=68, change_percent=3, ema20_distance_pct=4, macd_hist=2, sentiment=0.6),
        _candidate("BBB", rsi=35, change_percent=-3, ema20_distance_pct=-4, macd_hist=-2, sentiment=-0.6),
        _candidate("CCC", rsi=50),
    ])
    watch = select_watchlist(recs, top_n=5)
    alerts = select_risk_alerts(recs)
    assert all(r.action == "watch" for r in watch)
    assert all(r.action == "avoid" for r in alerts)
    assert "AAA" in [r.symbol for r in watch]
    assert "BBB" in [r.symbol for r in alerts]
