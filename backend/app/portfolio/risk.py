"""Static-current-holdings portfolio risk, stress, and contribution analytics."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

import numpy as np

from app.portfolio.schemas import (
    CorrelationCellOut,
    HoldingRiskContributionOut,
    PortfolioRiskOut,
    RegimeSensitivityOut,
    SectorDeviationOut,
    StressScenarioOut,
)

MIN_OBSERVATIONS = 30
ANNUAL_SESSIONS = 252


@dataclass(frozen=True)
class RiskHoldingInput:
    symbol: str
    sector: str
    quantity: float
    current_price: float | None
    closes: tuple[tuple[date, float], ...]

    @property
    def market_value(self) -> float | None:
        return (
            self.quantity * self.current_price if self.current_price is not None else None
        )


def _returns(closes: tuple[tuple[date, float], ...]) -> dict[date, float]:
    output: dict[date, float] = {}
    ordered = sorted(closes)
    for index in range(1, len(ordered)):
        prior = ordered[index - 1][1]
        if prior > 0:
            output[ordered[index][0]] = ordered[index][1] / prior - 1
    return output


def _max_drawdown(returns: np.ndarray) -> float:
    wealth = np.cumprod(1 + returns)
    peaks = np.maximum.accumulate(np.concatenate(([1.0], wealth)))[1:]
    return float(np.max(1 - wealth / peaks) * 100) if len(wealth) else 0.0


def _stress(
    total_value: float | None,
    weights: dict[str, float],
    sectors: dict[str, str],
    beta: float | None,
    volatility: float | None,
) -> list[StressScenarioOut]:
    sector_weight: dict[str, float] = defaultdict(float)
    for symbol, weight in weights.items():
        sector_weight[sectors[symbol]] += weight

    def scenario(
        code: str, label: str, shock: str, impact: float | None, methodology: str
    ) -> StressScenarioOut:
        return StressScenarioOut(
            code=code,
            label=label,
            shock=shock,
            estimated_impact_percent=round(impact, 4) if impact is not None else None,
            estimated_value_change=(
                round(total_value * impact / 100, 2)
                if total_value is not None and impact is not None
                else None
            ),
            methodology=methodology,
        )

    crude_impact = sum(
        weight
        * (
            {"Energy": 5.0, "Consumer Cyclical": -1.0, "Industrials": -1.0}.get(
                sector, 0.0
            )
        )
        for sector, weight in sector_weight.items()
    )
    currency_impact = sum(
        weight
        * (
            {"Technology": 2.0, "Energy": -2.0, "Consumer Defensive": -1.0}.get(
                sector, 0.0
            )
        )
        for sector, weight in sector_weight.items()
    )
    financial_weight = sum(
        weight for sector, weight in sector_weight.items() if "Financial" in sector
    )
    return [
        scenario(
            "nifty_down_5",
            "Broad market sell-off",
            "NIFTY -5%",
            beta * -5 if beta is not None else None,
            "Portfolio beta × -5%; linear single-factor estimate.",
        ),
        scenario(
            "crude_up_10",
            "Crude oil shock",
            "Crude +10%",
            crude_impact,
            "Sector shock assumptions: Energy +5%, Consumer Cyclical and Industrials -1%.",
        ),
        scenario(
            "inr_down_5",
            "Currency shock",
            "USD/INR +5%",
            currency_impact,
            "Sector shock assumptions: Technology +2%, Energy -2%, Consumer Defensive -1%.",
        ),
        scenario(
            "financials_down_7",
            "Financial-sector underperformance",
            "Financials -7%",
            financial_weight * -7,
            "Current Financial-sector weight × -7%.",
        ),
        scenario(
            "volatility_shift",
            "Volatility regime shift",
            "One annualized volatility unit adverse move",
            -volatility if volatility is not None else None,
            "Current static-weight annualized volatility applied as an adverse scenario.",
        ),
    ]


def compute_portfolio_risk(
    portfolio_id: int,
    holdings: list[RiskHoldingInput],
    benchmark_closes: tuple[tuple[date, float], ...],
    benchmark_sector_weights: dict[str, float],
    regime_by_date: dict[date, str],
    *,
    benchmark_symbol: str = "^NSEI",
) -> PortfolioRiskOut:
    values = {item.symbol: item.market_value for item in holdings}
    complete_values = all(value is not None and value >= 0 for value in values.values())
    total_value = (
        sum(float(value) for value in values.values() if value is not None)
        if complete_values
        else None
    )
    weights = (
        {
            symbol: float(value) / total_value
            for symbol, value in values.items()
            if value is not None
        }
        if total_value
        else {}
    )
    sectors = {item.symbol: item.sector for item in holdings}
    stock_returns = {item.symbol: _returns(item.closes) for item in holdings}
    benchmark_returns = _returns(benchmark_closes)
    missing = sorted(
        symbol for symbol, rows in stock_returns.items() if len(rows) < MIN_OBSERVATIONS
    )
    common_dates = set(benchmark_returns) if holdings else set()
    for rows in stock_returns.values():
        common_dates &= set(rows)
    dates = sorted(common_dates)
    complete = (
        complete_values
        and len(dates) >= MIN_OBSERVATIONS
        and not missing
        and bool(weights)
    )

    portfolio_returns = (
        np.asarray(
            [
                sum(
                    weights[symbol] * stock_returns[symbol][day]
                    for symbol in sorted(weights)
                )
                for day in dates
            ],
            dtype="float64",
        )
        if complete
        else np.asarray([], dtype="float64")
    )
    benchmark_array = (
        np.asarray([benchmark_returns[day] for day in dates], dtype="float64")
        if complete
        else np.asarray([], dtype="float64")
    )
    volatility = (
        float(np.std(portfolio_returns, ddof=1) * math.sqrt(ANNUAL_SESSIONS) * 100)
        if len(portfolio_returns) >= 2
        else None
    )
    std = float(np.std(portfolio_returns, ddof=1)) if len(portfolio_returns) >= 2 else 0.0
    sharpe = (
        float(np.mean(portfolio_returns) / std * math.sqrt(ANNUAL_SESSIONS))
        if std > 0
        else None
    )
    benchmark_variance = (
        float(np.var(benchmark_array, ddof=1)) if len(benchmark_array) >= 2 else 0.0
    )
    beta = (
        float(
            np.cov(portfolio_returns, benchmark_array, ddof=1)[0, 1] / benchmark_variance
        )
        if benchmark_variance > 0
        else None
    )
    drawdown = _max_drawdown(portfolio_returns) if len(portfolio_returns) else None

    correlation = []
    symbols = sorted(stock_returns)
    for symbol_x in symbols:
        for symbol_y in symbols:
            pair_dates = sorted(
                set(stock_returns[symbol_x]) & set(stock_returns[symbol_y])
            )
            value = None
            if len(pair_dates) >= MIN_OBSERVATIONS:
                left = np.asarray([stock_returns[symbol_x][day] for day in pair_dates])
                right = np.asarray([stock_returns[symbol_y][day] for day in pair_dates])
                left_std, right_std = np.std(left), np.std(right)
                value = (
                    float(np.corrcoef(left, right)[0, 1])
                    if left_std > 0 and right_std > 0
                    else (1.0 if symbol_x == symbol_y else None)
                )
            correlation.append(
                CorrelationCellOut(
                    symbol_x=symbol_x,
                    symbol_y=symbol_y,
                    correlation=round(value, 6) if value is not None else None,
                    observations=len(pair_dates),
                )
            )

    contributions = []
    covariance_matrix = (
        np.cov(
            np.asarray(
                [[stock_returns[symbol][day] for symbol in symbols] for day in dates]
            ),
            rowvar=False,
            ddof=1,
        )
        if complete and len(symbols) > 1
        else None
    )
    portfolio_variance = (
        float(np.var(portfolio_returns, ddof=1)) if len(portfolio_returns) >= 2 else 0.0
    )
    for index, symbol in enumerate(symbols):
        rows = stock_returns[symbol]
        recent_dates = sorted(rows)[-20:]
        momentum = (
            math.prod(1 + rows[day] for day in recent_dates) - 1
            if len(recent_dates) == 20
            else None
        )
        return_contribution = (
            weights.get(symbol, 0)
            * statistics.fmean(rows[day] for day in dates)
            * ANNUAL_SESSIONS
            * 100
            if complete
            else None
        )
        if complete and portfolio_variance > 0:
            if len(symbols) == 1:
                risk_contribution = 100.0
            else:
                weight_vector = np.asarray([weights[item] for item in symbols])
                marginal = float(np.asarray(covariance_matrix)[index] @ weight_vector)
                risk_contribution = weights[symbol] * marginal / portfolio_variance * 100
        else:
            risk_contribution = None
        contributions.append(
            HoldingRiskContributionOut(
                symbol=symbol,
                weight_percent=round(weights.get(symbol, 0) * 100, 4),
                return_contribution_percent=round(return_contribution, 4)
                if return_contribution is not None
                else None,
                risk_contribution_percent=round(risk_contribution, 4)
                if risk_contribution is not None
                else None,
                momentum_20d_percent=round(momentum * 100, 4)
                if momentum is not None
                else None,
            )
        )

    portfolio_sector: dict[str, float] = defaultdict(float)
    for symbol, weight in weights.items():
        portfolio_sector[sectors[symbol]] += weight * 100
    sector_deviation = [
        SectorDeviationOut(
            sector=sector,
            portfolio_weight_percent=round(portfolio_sector.get(sector, 0), 4),
            benchmark_weight_percent=round(benchmark_sector_weights.get(sector, 0), 4),
            deviation_percent=round(
                portfolio_sector.get(sector, 0) - benchmark_sector_weights.get(sector, 0),
                4,
            ),
        )
        for sector in sorted(set(portfolio_sector) | set(benchmark_sector_weights))
    ]

    regimes: dict[str, list[float]] = defaultdict(list)
    for day, value in zip(dates if complete else [], portfolio_returns, strict=True):
        regimes[regime_by_date.get(day, "unavailable")].append(float(value))
    regime_sensitivity = [
        RegimeSensitivityOut(
            regime=label,
            sessions=len(rows),
            average_daily_return_percent=round(statistics.fmean(rows) * 100, 6),
            positive_session_percent=round(
                sum(value > 0 for value in rows) / len(rows) * 100, 4
            ),
        )
        for label, rows in sorted(regimes.items())
    ]
    momentum_exposure = (
        sum(
            (item.momentum_20d_percent or 0) * item.weight_percent / 100
            for item in contributions
            if item.momentum_20d_percent is not None
        )
        if contributions
        and all(item.momentum_20d_percent is not None for item in contributions)
        else None
    )

    return PortfolioRiskOut(
        portfolio_id=portfolio_id,
        as_of=max((day for item in holdings for day, _ in item.closes), default=None),
        methodology="Static current-quantity/current-value weights applied to aligned historical close returns; not actual portfolio performance.",
        benchmark_symbol=benchmark_symbol,
        observations=len(dates),
        minimum_observations=MIN_OBSERVATIONS,
        data_complete=complete,
        missing_symbols=missing,
        annualized_volatility_percent=round(volatility, 4)
        if volatility is not None
        else None,
        beta=round(beta, 6) if beta is not None else None,
        sharpe_ratio=round(sharpe, 6) if sharpe is not None else None,
        max_drawdown_percent=round(drawdown, 4) if drawdown is not None else None,
        concentration_hhi=round(sum(weight**2 for weight in weights.values()), 6)
        if weights
        else None,
        momentum_exposure_percent=round(momentum_exposure, 4)
        if momentum_exposure is not None
        else None,
        correlation=correlation,
        holding_contributions=contributions,
        sector_deviation=sector_deviation,
        sector_benchmark_methodology="NIFTY 100 current constituent market-cap weights; equal-weight fallback when market-cap coverage is incomplete.",
        regime_sensitivity=regime_sensitivity,
        stress_scenarios=_stress(total_value, weights, sectors, beta, volatility),
    )
