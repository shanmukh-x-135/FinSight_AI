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


class SimilarSessionOut(SessionSummary):
    similarity_score: float
    distance: float
    next_day_return: float | None
    outcome: str | None


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
    query_date: date
    query_summary: SessionSummary
    similar_sessions: list[SimilarSessionOut]
    statistics: StatisticsOut


class RebuildResult(BaseModel):
    sessions_indexed: int
    dim: int
    latest_date: date | None
