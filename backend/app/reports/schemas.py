"""Pydantic schemas for the reports endpoints.

The report read shapes mirror Phase 6 (unchanged contract). Filtering and
pagination are Phase 8 additions, supplied as query parameters.
"""

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
