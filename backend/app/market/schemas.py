"""Pydantic response schemas for the market read endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class IngestionResult(BaseModel):
    """Summary returned by the manual ingestion trigger."""

    requested: int
    succeeded: list[str]
    failed: list[str]
    price_bars_fetched: int = 0
    bootstrap_symbols: int = 0
    reconciliation_symbols: int = 0
    incremental_symbols: int = 0


class FundamentalsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    market_cap: int | None = None
    pe_ratio: float | None = None
    eps: float | None = None
    dividend_yield: float | None = None
    week52_high: float | None = None
    week52_low: float | None = None


class QuoteOut(BaseModel):
    """Latest price snapshot for a stock, with day-over-day change."""

    symbol: str
    name: str | None
    sector: str | None
    date: date | None
    close: float | None
    previous_close: float | None
    change: float | None
    change_percent: float | None
    volume: int | None


class StockDetailOut(QuoteOut):
    industry: str | None
    exchange: str | None
    fundamentals: FundamentalsOut | None


class IndicatorPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    rsi_14: float | None
    ema_20: float | None
    ema_50: float | None
    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None
    bb_upper: float | None
    bb_middle: float | None
    bb_lower: float | None
    atr_14: float | None


class SectorPerformanceOut(BaseModel):
    sector: str
    stock_count: int
    average_change_percent: float | None
    stocks: list[QuoteOut]


class SectorOverviewOut(BaseModel):
    """One tile in the market-wide sector heatmap (Phase 7 dashboard/market)."""

    sector: str
    stock_count: int
    average_change_percent: float | None


class BreadthOut(BaseModel):
    """Market breadth: advancers vs decliners across the tracked universe."""

    advancers: int
    decliners: int
    unchanged: int
    total: int
    advance_decline_ratio: float | None


class TechnicalSummaryOut(BaseModel):
    as_of: date | None
    stocks_with_indicators: int
    average_rsi: float | None
    bullish_rsi_count: int
    overbought_count: int
    oversold_count: int
    above_ema20_count: int
    above_ema50_count: int
    positive_macd_count: int
    average_atr_percent: float | None


class EconomicEventOut(BaseModel):
    event_id: str
    date: datetime
    country: str
    category: str
    name: str
    importance: int
    reference: str | None
    source: str | None
    source_url: str | None
    actual: str | None
    forecast: str | None
    previous: str | None


class EconomicCalendarOut(BaseModel):
    provider: str = "Trading Economics"
    status: Literal["ok", "not_configured", "unavailable"]
    events: list[EconomicEventOut]
