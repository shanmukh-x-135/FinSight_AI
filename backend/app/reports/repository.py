"""Data-access for the reports domain — filtered, paginated listing + detail.

Reuses Phase 6's ``reports`` table (no schema change). A user sees their own
reports plus global (user-less) market reports.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.models import Report


class ReportRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_report(self, report_id: int) -> Report | None:
        result = await self.db.execute(select(Report).where(Report.id == report_id))
        return result.scalar_one_or_none()

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
        stmt = select(Report).where(
            (Report.user_id == user_id) | (Report.user_id.is_(None))
        )
        if report_type:
            stmt = stmt.where(Report.report_type == report_type)
        if start_date:
            start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
            stmt = stmt.where(Report.created_at >= start_dt)
        if end_date:
            # Inclusive of the whole end day.
            end_dt = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
            stmt = stmt.where(Report.created_at < end_dt)

        stmt = (
            stmt.order_by(Report.created_at.desc(), Report.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
