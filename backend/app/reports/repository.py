"""Data-access for report creation, idempotent retries, listing, and detail.

A user sees their own reports plus global (user-less) market reports.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.models import Report
from app.shared.upsert import conflict_insert


class ReportRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_report(
        self,
        user_id: int | None,
        report_type: str,
        sections: dict,
        *,
        idempotency_key_hash: str | None = None,
    ) -> Report:
        if idempotency_key_hash is not None:
            stmt = conflict_insert(self.db, Report).values(
                user_id=user_id,
                report_type=report_type,
                sections=sections,
                idempotency_key_hash=idempotency_key_hash,
            )
            result = await self.db.execute(
                stmt.on_conflict_do_nothing(
                    index_elements=[Report.idempotency_key_hash]
                ).returning(Report.id)
            )
            report_id = result.scalar_one_or_none()
            if report_id is None:
                existing = await self.get_by_idempotency_hash(idempotency_key_hash)
                if existing is None:  # Defensive: conflict target guarantees a row.
                    raise RuntimeError("Idempotent report insert lost without a winner")
                return existing
            report = await self.get_report(report_id)
            if report is None:  # Defensive: RETURNING supplied a persisted id.
                raise RuntimeError("Inserted report could not be reloaded")
            return report

        report = Report(user_id=user_id, report_type=report_type, sections=sections)
        self.db.add(report)
        await self.db.flush()
        return report

    async def get_by_idempotency_hash(self, key_hash: str) -> Report | None:
        result = await self.db.execute(
            select(Report).where(Report.idempotency_key_hash == key_hash)
        )
        return result.scalar_one_or_none()

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
