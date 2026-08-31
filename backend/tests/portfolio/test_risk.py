"""Controlled fixtures for advanced portfolio risk and scenario analytics."""

from __future__ import annotations

import math
import statistics
from datetime import date, timedelta

import pytest

from app.portfolio.risk import RiskHoldingInput, compute_portfolio_risk

START = date(2025, 1, 1)


def _closes(returns: list[float], start: float = 100.0) -> tuple[tuple[date, float], ...]:
    values = [(START, start)]
    price = start
    for index, value in enumerate(returns, start=1):
        price *= 1 + value
        values.append((START + timedelta(days=index), price))
    return tuple(values)


def test_single_asset_equal_to_benchmark_matches_hand_calculation() -> None:
    returns = [0.01, -0.005] * 20
    closes = _closes(returns)
    holding = RiskHoldingInput(
        symbol="AAA.NS",
        sector="Technology",
        quantity=10,
        current_price=closes[-1][1],
        closes=closes,
    )

    result = compute_portfolio_risk(
        1,
        [holding],
        closes,
        {"Technology": 60, "Financial Services": 40},
        {START + timedelta(days=index): "mixed" for index in range(1, 41)},
    )

    expected_volatility = statistics.stdev(returns) * math.sqrt(252) * 100
    expected_sharpe = statistics.fmean(returns) / statistics.stdev(returns) * math.sqrt(252)
    assert result.data_complete is True
    assert result.observations == 40
    assert result.beta == pytest.approx(1)
    assert result.annualized_volatility_percent == pytest.approx(expected_volatility, abs=1e-4)
    assert result.sharpe_ratio == pytest.approx(expected_sharpe, abs=1e-6)
    assert result.max_drawdown_percent == pytest.approx(0.5)
    assert result.concentration_hhi == pytest.approx(1)
    assert result.correlation[0].correlation == pytest.approx(1)
    assert result.holding_contributions[0].risk_contribution_percent == pytest.approx(100)
    assert result.sector_deviation[1].deviation_percent == pytest.approx(40)
    nifty = next(item for item in result.stress_scenarios if item.code == "nifty_down_5")
    assert nifty.estimated_impact_percent == pytest.approx(-5)
    assert nifty.is_prediction is False
    assert all("static" in result.methodology.lower() for _ in [0])


def test_insufficient_history_is_safe_and_explicit() -> None:
    closes = _closes([0.01] * 10)
    result = compute_portfolio_risk(
        2,
        [RiskHoldingInput("SHORT.NS", "Energy", 2, closes[-1][1], closes)],
        closes,
        {},
        {},
    )

    assert result.data_complete is False
    assert result.missing_symbols == ["SHORT.NS"]
    assert result.beta is None
    assert result.annualized_volatility_percent is None
    assert result.sharpe_ratio is None
    assert result.max_drawdown_percent is None
    assert result.correlation[0].correlation is None
    assert next(
        item for item in result.stress_scenarios if item.code == "nifty_down_5"
    ).estimated_impact_percent is None
