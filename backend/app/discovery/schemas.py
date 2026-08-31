"""Validated contracts for natural-language discovery."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ScreenerField = Literal[
    "sector",
    "price_change_percent",
    "rsi_14",
    "price_vs_ema20",
    "price_vs_ema50",
    "macd_histogram",
    "volume_ratio",
    "pe_ratio",
    "eps",
    "news_sentiment",
    "signal_state",
    "regime_fit",
]
ScreenerOperator = Literal[
    "eq",
    "gt",
    "gte",
    "lt",
    "lte",
    "between",
    "positive",
    "negative",
    "non_negative",
    "above",
    "below",
]


class ScreenerCondition(BaseModel):
    field: ScreenerField
    operator: ScreenerOperator
    value: float | str | None = None
    upper_value: float | None = None


class ScreenerAST(BaseModel):
    version: Literal["screener_ast_v1"] = "screener_ast_v1"
    universe: Literal["NIFTY50", "NIFTYNEXT50", "NIFTY100"] = "NIFTY100"
    conditions: list[ScreenerCondition] = Field(min_length=1, max_length=20)


class ScreenerQuery(BaseModel):
    query: str = Field(min_length=3, max_length=1000)


class ScreenerRow(BaseModel):
    symbol: str
    name: str | None
    sector: str | None
    as_of: date | None
    close: float | None
    price_change_percent: float | None
    rsi_14: float | None
    ema_20: float | None
    ema_50: float | None
    macd_histogram: float | None
    volume_ratio: float | None
    pe_ratio: float | None
    eps: float | None
    news_sentiment: float | None
    signal_state: str
    regime_fit: str


class ScreenerResult(BaseModel):
    query: str
    ast: ScreenerAST
    explanation: list[str]
    rows: list[ScreenerRow]
    result_hash: str


class SavedScreenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    query_text: str = Field(min_length=3, max_length=1000)
    filter_ast: ScreenerAST


class SavedScreenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    query_text: str
    filter_ast: ScreenerAST
    created_at: datetime
    updated_at: datetime
