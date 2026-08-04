"""Pydantic schemas for the intelligence endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReportSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_type: str
    created_at: datetime


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    report_type: str
    sections: dict
    created_at: datetime


class RecommendationsOut(BaseModel):
    watchlist: list[dict]
    risk_alerts: list[dict]
