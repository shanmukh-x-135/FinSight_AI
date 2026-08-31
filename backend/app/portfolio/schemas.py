"""Pydantic request/response schemas for portfolio & watchlist endpoints."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------- #
# Requests                                                                     #
# --------------------------------------------------------------------------- #
class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120, default="My Portfolio")


class PortfolioUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class HoldingCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    quantity: float = Field(gt=0)
    avg_buy_price: float = Field(gt=0)


class HoldingUpdate(BaseModel):
    quantity: float | None = Field(default=None, gt=0)
    avg_buy_price: float | None = Field(default=None, gt=0)


class WatchlistAdd(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    pinned: bool = False


class WatchlistUpdate(BaseModel):
    pinned: bool | None = None
    sort_order: int | None = None


# --------------------------------------------------------------------------- #
# Responses                                                                    #
# --------------------------------------------------------------------------- #
class HoldingOut(BaseModel):
    """A raw holding (for editing) — no live valuation."""

    id: int
    symbol: str
    name: str | None
    sector: str | None
    quantity: float
    avg_buy_price: float


class PortfolioSummaryOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    holding_count: int


class PortfolioDetailOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    holdings: list[HoldingOut]


class HoldingAnalyticsOut(BaseModel):
    id: int
    symbol: str
    name: str | None
    sector: str | None
    quantity: float
    avg_buy_price: float
    current_price: float | None
    previous_close: float | None
    market_value: float | None
    cost_basis: float
    unrealized_pnl: float | None
    return_percent: float | None
    daily_pnl: float | None
    weight_percent: float | None


class SectorAllocationOut(BaseModel):
    sector: str
    value: float
    weight_percent: float


class PortfolioAnalyticsOut(BaseModel):
    portfolio_id: int
    name: str
    total_value: float | None
    total_cost: float
    total_unrealized_pnl: float | None
    total_return_percent: float | None
    daily_pnl: float | None
    daily_pnl_percent: float | None
    number_of_holdings: int
    number_of_sectors: int
    top_holding_weight_percent: float | None
    concentration_hhi: float | None
    diversification_score: float | None
    volatility_percent: float | None
    health_score: float | None
    risk_level: str
    valuation_complete: bool
    unpriced_symbols: list[str]
    sector_allocation: list[SectorAllocationOut]
    holdings: list[HoldingAnalyticsOut]


class CorrelationCellOut(BaseModel):
    symbol_x: str
    symbol_y: str
    correlation: float | None
    observations: int


class HoldingRiskContributionOut(BaseModel):
    symbol: str
    weight_percent: float
    return_contribution_percent: float | None
    risk_contribution_percent: float | None
    momentum_20d_percent: float | None


class SectorDeviationOut(BaseModel):
    sector: str
    portfolio_weight_percent: float
    benchmark_weight_percent: float
    deviation_percent: float


class RegimeSensitivityOut(BaseModel):
    regime: str
    sessions: int
    average_daily_return_percent: float
    positive_session_percent: float


class StressScenarioOut(BaseModel):
    code: str
    label: str
    shock: str
    estimated_impact_percent: float | None
    estimated_value_change: float | None
    methodology: str
    is_prediction: bool = False


class PortfolioRiskOut(BaseModel):
    portfolio_id: int
    as_of: date | None
    methodology: str
    benchmark_symbol: str
    observations: int
    minimum_observations: int
    data_complete: bool
    missing_symbols: list[str]
    annualized_volatility_percent: float | None
    beta: float | None
    sharpe_ratio: float | None
    max_drawdown_percent: float | None
    concentration_hhi: float | None
    momentum_exposure_percent: float | None
    correlation: list[CorrelationCellOut]
    holding_contributions: list[HoldingRiskContributionOut]
    sector_deviation: list[SectorDeviationOut]
    sector_benchmark_methodology: str
    regime_sensitivity: list[RegimeSensitivityOut]
    stress_scenarios: list[StressScenarioOut]


class CounterfactualChange(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    quantity_delta: float


class CounterfactualRequest(BaseModel):
    changes: list[CounterfactualChange] = Field(min_length=1, max_length=20)


class CounterfactualOut(BaseModel):
    label: str = "Scenario estimate, not a prediction"
    changes: list[CounterfactualChange]
    before: PortfolioRiskOut
    after: PortfolioRiskOut
    deltas: dict[str, float | None]


class WatchlistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    name: str | None
    sector: str | None
    current_price: float | None
    previous_close: float | None
    change: float | None
    change_percent: float | None
    rsi_14: float | None
    trend: str | None
    pinned: bool
    sort_order: int
