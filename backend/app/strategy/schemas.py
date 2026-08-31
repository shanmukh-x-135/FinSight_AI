"""Validated strategy DSL and API response schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Union

from pydantic import BaseModel, Field, model_validator

NumericField = Literal[
    "rsi",
    "macd_histogram",
    "volume_ratio",
    "sector_momentum_20d",
    "market_breadth",
    "news_sentiment",
]
RuleField = Literal[
    "price_vs_ema20",
    "price_vs_ema50",
    "rsi",
    "macd_histogram",
    "volume_ratio",
    "sector_momentum_20d",
    "market_breadth",
    "market_regime",
    "news_sentiment",
]
RuleOperator = Literal[
    "gt",
    "gte",
    "lt",
    "lte",
    "between",
    "positive",
    "negative",
    "above",
    "below",
    "is",
    "is_not",
]
UniverseCode = Literal["NIFTY50", "NIFTYNEXT50", "NIFTY100"]
MembershipMode = Literal["current_universe", "historical_membership"]


class RuleCondition(BaseModel):
    kind: Literal["condition"] = "condition"
    field: RuleField
    operator: RuleOperator
    value: float | str | None = None
    upper_value: float | None = None

    @model_validator(mode="after")
    def validate_field_operator(self) -> "RuleCondition":
        if self.field in {"price_vs_ema20", "price_vs_ema50"}:
            if self.operator not in {"above", "below"} or self.value is not None:
                raise ValueError("Price/EMA rules require above or below without a value")
            return self
        if self.field == "market_regime":
            if self.operator not in {"is", "is_not"} or not isinstance(self.value, str):
                raise ValueError("Market-regime rules require is/is_not and a label")
            if self.value not in {"broad_positive", "broad_negative", "mixed"}:
                raise ValueError("Unsupported market regime")
            return self
        if self.operator in {"positive", "negative"}:
            if self.field != "macd_histogram" or self.value is not None:
                raise ValueError("State rules apply only to MACD histogram")
            return self
        if self.operator not in {"gt", "gte", "lt", "lte", "between"}:
            raise ValueError("Numeric rule requires a numeric comparison operator")
        if not isinstance(self.value, (int, float)):
            raise ValueError("Numeric rule requires a numeric value")
        if self.operator == "between":
            if self.upper_value is None or self.upper_value < float(self.value):
                raise ValueError(
                    "Between requires upper_value greater than or equal to value"
                )
        elif self.upper_value is not None:
            raise ValueError("upper_value is valid only for between")
        return self


class RuleGroup(BaseModel):
    kind: Literal["group"] = "group"
    operator: Literal["AND", "OR", "NOT"]
    rules: list[Union[RuleCondition, "RuleGroup"]] = Field(
        min_length=1, max_length=20
    )

    @model_validator(mode="after")
    def validate_not_arity(self) -> "RuleGroup":
        if self.operator == "NOT" and len(self.rules) != 1:
            raise ValueError("NOT requires exactly one child rule")
        return self


RuleGroup.model_rebuild()


class ExecutionConfig(BaseModel):
    initial_capital: float = Field(default=100_000.0, gt=0, le=1_000_000_000)
    max_positions: int = Field(default=10, ge=1, le=100)
    transaction_cost_bps: float = Field(default=10.0, ge=0, le=500)
    slippage_bps: float = Field(default=5.0, ge=0, le=500)
    stop_loss_percent: float | None = Field(default=None, gt=0, le=100)
    take_profit_percent: float | None = Field(default=None, gt=0, le=1000)
    max_holding_sessions: int | None = Field(default=None, ge=1, le=1260)
    benchmark_symbol: str = Field(default="^NSEI", min_length=1, max_length=32)


class StrategyDefinition(BaseModel):
    entry: RuleGroup
    exit: RuleGroup
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)


class StrategyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    definition: StrategyDefinition


class StrategyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    definition: StrategyDefinition


class StrategyVersionOut(BaseModel):
    id: int
    version: int
    definition: StrategyDefinition
    created_at: datetime


class StrategyOut(BaseModel):
    id: int
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    latest_version: StrategyVersionOut


class BacktestCreate(BaseModel):
    start_date: date
    end_date: date
    universe_code: UniverseCode = "NIFTY100"
    membership_mode: MembershipMode = "current_universe"

    @model_validator(mode="after")
    def validate_dates(self) -> "BacktestCreate":
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        if (self.end_date - self.start_date).days > 3653:
            raise ValueError("Backtest range cannot exceed ten years")
        return self


class EquityPointOut(BaseModel):
    date: date
    equity: float
    benchmark_equity: float | None
    drawdown_percent: float


class BacktestTradeOut(BaseModel):
    symbol: str
    entry_signal_date: date
    entry_date: date
    entry_price: float
    exit_signal_date: date | None
    exit_date: date
    exit_price: float
    quantity: int
    gross_pnl: float
    net_pnl: float
    return_percent: float
    holding_sessions: int
    exit_reason: str
    transaction_cost: float


class BacktestMetricsOut(BaseModel):
    total_return_percent: float
    benchmark_return_percent: float | None
    excess_return_percent: float | None
    cagr_percent: float | None
    sharpe_ratio: float | None
    sortino_ratio: float | None
    max_drawdown_percent: float
    win_rate_percent: float | None
    profit_factor: float | None
    average_winner_percent: float | None
    average_loser_percent: float | None
    expectancy_percent: float | None
    total_trades: int
    average_holding_sessions: float | None
    turnover_percent: float
    estimated_transaction_costs: float


class BacktestOut(BaseModel):
    id: int
    strategy_id: int
    strategy_version_id: int
    strategy_version: int
    status: Literal["completed", "failed"]
    start_date: date
    end_date: date
    universe_code: UniverseCode
    membership_mode: MembershipMode
    membership_disclaimer: str
    benchmark_symbol: str
    result_hash: str | None
    created_at: datetime
    completed_at: datetime | None
    metrics: BacktestMetricsOut | None
    equity_curve: list[EquityPointOut]
    trades: list[BacktestTradeOut]
    robustness_analysis: dict | None = None


class BacktestSummaryOut(BaseModel):
    id: int
    strategy_version: int
    status: Literal["completed", "failed"]
    start_date: date
    end_date: date
    universe_code: UniverseCode
    membership_mode: MembershipMode
    result_hash: str | None
    created_at: datetime
    metrics: BacktestMetricsOut | None
