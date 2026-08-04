"""Reports service — generation (delegated), listing, detail, and export.

Generation stays in the intelligence layer (the AI pipeline); this service owns
the browse/detail/export workflow. Export renders the stored structured sections
on demand — Markdown first (single source of truth), then PDF from that Markdown.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.models import Report
from app.intelligence.service import IntelligenceService
from app.reports.exceptions import ReportNotFoundError, UnsupportedExportFormatError
from app.reports.exporters import render_markdown, render_pdf
from app.reports.repository import ReportRepository


class ReportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = ReportRepository(db)

    async def generate(self, user_id: int | None, report_type: str = "daily") -> Report:
        # Generation is the intelligence pipeline's responsibility.
        return await IntelligenceService(self.db).generate_report(user_id, report_type)

    async def list_reports(
        self,
        user_id: int,
        *,
        report_type: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Report]:
        return await self.repo.list_reports(
            user_id,
            report_type=report_type,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

    async def get_report(self, report_id: int, user_id: int) -> Report:
        report = await self.repo.get_report(report_id)
        # Not-found or a user-scoped report owned by someone else → 404.
        if report is None or (report.user_id is not None and report.user_id != user_id):
            raise ReportNotFoundError()
        return report

    async def export(
        self, report_id: int, user_id: int, fmt: str
    ) -> tuple[bytes, str, str]:
        """Return (content_bytes, media_type, filename) for the requested format."""
        report = await self.get_report(report_id, user_id)
        markdown = render_markdown(report)
        stem = f"finsight-report-{report.id}"
        if fmt == "markdown":
            return markdown.encode("utf-8"), "text/markdown; charset=utf-8", f"{stem}.md"
        if fmt == "pdf":
            return render_pdf(markdown), "application/pdf", f"{stem}.pdf"
        raise UnsupportedExportFormatError(fmt)
