"""Data-access for the intelligence domain (reports)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.models import Report


class IntelligenceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_report(
        self, user_id: int | None, report_type: str, sections: dict
    ) -> Report:
        report = Report(user_id=user_id, report_type=report_type, sections=sections)
        self.db.add(report)
        await self.db.flush()
        return report

    async def get_report(self, report_id: int) -> Report | None:
        result = await self.db.execute(select(Report).where(Report.id == report_id))
        return result.scalar_one_or_none()

    async def list_reports(self, user_id: int, limit: int = 50) -> list[Report]:
        result = await self.db.execute(
            select(Report)
            .where((Report.user_id == user_id) | (Report.user_id.is_(None)))
            .order_by(Report.created_at.desc(), Report.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
