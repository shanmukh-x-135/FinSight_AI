"""Unit tests for the deterministic narrative fallbacks (prompt builder)."""

from __future__ import annotations

from app.intelligence import prompt_builder as pb


def test_market_fallback_reflects_breadth() -> None:
    slice_ = {
        "breadth": {"advancers": 3, "decliners": 1, "unchanged": 0, "total": 4,
                    "advance_decline_ratio": 3.0},
        "gainers": [{"symbol": "AAA.NS", "change_percent": 5.0}],
        "losers": [{"symbol": "BBB.NS", "change_percent": -4.0}],
    }
    _prompt, fallback = pb.market_section(slice_)
    assert "3 advancers" in fallback and "1 decliners" in fallback
    assert "AAA.NS" in fallback and "BBB.NS" in fallback


def test_historical_fallback_with_and_without_sample() -> None:
    with_sample = {
        "similar_sessions": [{}, {}, {}],
        "statistics": {"sample_size": 3, "bullish_probability": 0.667,
                       "avg_next_day_return": 0.01},
    }
    _p, fb = pb.historical_section(with_sample)
    assert "closed higher" in fb and "not a forecast" in fb

    empty = {"similar_sessions": [], "statistics": {"sample_size": 0,
             "bullish_probability": None, "avg_next_day_return": None}}
    _p2, fb2 = pb.historical_section(empty)
    assert "No comparable historical sessions" in fb2


def test_portfolio_fallback() -> None:
    slice_ = {
        "total_value": 19440.0, "total_return_percent": -3.5, "health_score": 46.9,
        "risk_level": "high", "diversification_score": 49.5, "number_of_holdings": 2,
    }
    _p, fb = pb.portfolio_section(slice_)
    assert "19,440" in fb and "high" in fb and "2 holdings" in fb


def test_executive_summary_combines_sections() -> None:
    sections = {
        "market_summary": {"narrative": "Market was mixed."},
        "recommendations": [{"symbol": "AAA.NS", "action": "watch"}],
    }
    prompt, fb = pb.executive_summary(sections)
    assert "Market was mixed." in fb
    assert "Watchlist: AAA.NS" in fb
    assert '"market": "Market was mixed."' in prompt
    assert '"watchlist": [' in prompt and '"AAA.NS"' in prompt
