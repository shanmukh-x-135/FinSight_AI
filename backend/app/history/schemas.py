"""Pydantic schemas for the historical-intelligence endpoints."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class SessionSummary(BaseModel):
    date: date
    avg_return: float
    pct_advancers: float
    advance_decline_ratio: float
    avg_rsi: float
    feature_version: str
    median_rsi: float
    median_atr_percent: float
    median_relative_volume: float
    coverage_ratio: float
    usable_constituents: int
    expected_constituents: int
    membership_mode: str
    quality_flags: list[str]
    breadth_regime: str
    momentum_regime: str
    volatility_regime: str


class FactorComparison(BaseModel):
    factor: str
    similarity_score: float
    explanation: str


class SimilarSessionOut(SessionSummary):
    similarity_score: float
    distance: float
    next_day_return: float | None
    outcome: str | None
    next_session_breadth: float | None
    forward_5_session_return: float | None
    forward_5_session_drawdown: float | None
    forward_5_session_upside: float | None
    matching_factors: list[FactorComparison]
    divergence_factors: list[FactorComparison]


class StatisticsOut(BaseModel):
    k: int
    sample_size: int
    bullish_count: int
    bearish_count: int
    neutral_count: int
    bullish_probability: float | None
    avg_next_day_return: float | None
    median_next_day_return: float | None
    std_next_day_return: float | None
    best_case_return: float | None
    worst_case_return: float | None
    ci_low: float | None
    ci_high: float | None


class SimilarityResponse(BaseModel):
    feature_version: str
    vector_dimension: int
    normalization_method: str
    query_date: date
    query_summary: SessionSummary
    similar_sessions: list[SimilarSessionOut]
    statistics: StatisticsOut


class RebuildResult(BaseModel):
    sessions_indexed: int
    dim: int
    latest_date: date | None
    feature_version: str
    normalization_method: str
    candidate_sessions: int
    rejected_sessions: int
    rejection_reasons: dict[str, int]
    build_duration_seconds: float
    approximate_index_bytes: int
