"""Intelligence HTTP routes (auth-protected).

Report generation + retrieval and current recommendations. Phase 8 adds report
listing filters and Markdown/PDF export on top of these.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.intelligence.schemas import (
    RecommendationsOut,
    ReportOut,
    ReportSummaryOut,
)
from app.intelligence.service import IntelligenceService
from app.shared.database import get_db
from app.shared.response import envelope

reports_router = APIRouter(prefix="/reports", tags=["reports"])
intelligence_router = APIRouter(tags=["intelligence"])


@reports_router.post(
    "/generate",
    status_code=status.HTTP_201_CREATED,
    summary="Generate an evidence-backed report for the current user",
)
async def generate_report(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    report = await IntelligenceService(db).generate_report(user.id)
    return envelope(data=ReportOut.model_validate(report), message="Report generated.")


@reports_router.get("", summary="List your reports")
async def list_reports(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    reports = await IntelligenceService(db).list_reports(user.id)
    return envelope(data=[ReportSummaryOut.model_validate(r) for r in reports])


@reports_router.get("/{report_id}", summary="Get a report")
async def get_report(
    report_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    report = await IntelligenceService(db).get_report(report_id, user.id)
    return envelope(data=ReportOut.model_validate(report))


@intelligence_router.get(
    "/recommendations",
    summary="Current watchlist recommendations + risk alerts (evidence-backed)",
)
async def recommendations(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    data = await IntelligenceService(db).get_recommendations(user.id)
    return envelope(data=RecommendationsOut(**data))
