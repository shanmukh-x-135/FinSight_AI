"""Reports HTTP routes (auth-protected).

Browse (filter + paginate), open, and export reports. Generation is exposed here
too for convenience, delegating to the intelligence pipeline. Export endpoints
return a downloadable file (not the JSON envelope) since the body is a document.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.reports.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.reports.schemas import ReportOut, ReportSummaryOut
from app.reports.service import ReportService
from app.shared.database import get_db
from app.shared.response import envelope

reports_router = APIRouter(prefix="/reports", tags=["reports"])


@reports_router.post(
    "/generate",
    status_code=status.HTTP_201_CREATED,
    summary="Generate an evidence-backed report for the current user",
)
async def generate_report(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=200,
            description="Opaque retry key; reuse it to receive the original report.",
        ),
    ] = None,
) -> dict:
    report = await ReportService(db).generate(
        user.id, idempotency_key=idempotency_key
    )
    return envelope(data=ReportOut.model_validate(report), message="Report generated.")


@reports_router.get("", summary="List your reports (filterable, paginated)")
async def list_reports(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    report_type: str | None = Query(default=None, description="Filter by report type"),
    start_date: date | None = Query(default=None, description="Created on/after (YYYY-MM-DD)"),
    end_date: date | None = Query(default=None, description="Created on/before (YYYY-MM-DD)"),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> dict:
    reports = await ReportService(db).list_reports(
        user.id,
        report_type=report_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    return envelope(data=[ReportSummaryOut.model_validate(r) for r in reports])


@reports_router.get("/{report_id}", summary="Get a report")
async def get_report(
    report_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    report = await ReportService(db).get_report(report_id, user.id)
    return envelope(data=ReportOut.model_validate(report))


@reports_router.get(
    "/{report_id}/export",
    summary="Export a report as Markdown or PDF (rendered on demand)",
)
async def export_report(
    report_id: int,
    fmt: str = Query(default="pdf", alias="format", description="markdown | pdf"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    content, media_type, filename = await ReportService(db).export(report_id, user.id, fmt)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
