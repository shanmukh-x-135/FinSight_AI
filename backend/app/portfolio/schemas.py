"""Pydantic request/response schemas for portfolio & watchlist endpoints."""

from __future__ import annotations

from datetime import datetime

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
    market_value: float
    cost_basis: float
    unrealized_pnl: float
    return_percent: float | None
    daily_pnl: float
    weight_percent: float


class SectorAllocationOut(BaseModel):
    sector: str
    value: float
    weight_percent: float


class PortfolioAnalyticsOut(BaseModel):
    portfolio_id: int
    name: str
    total_value: float
    total_cost: float
    total_unrealized_pnl: float
    total_return_percent: float | None
    daily_pnl: float
    daily_pnl_percent: float | None
    number_of_holdings: int
    number_of_sectors: int
    top_holding_weight_percent: float
    concentration_hhi: float
    diversification_score: float
    volatility_percent: float | None
    health_score: float
    risk_level: str
    sector_allocation: list[SectorAllocationOut]
    holdings: list[HoldingAnalyticsOut]


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
    pinned: bool
    sort_order: int
