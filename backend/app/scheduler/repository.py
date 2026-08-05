"""Persistence operations for pipeline execution state."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.scheduler.models import PipelineRun, PipelineRunStep


class PipelineRunRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_run(
        self, pipeline_name: str, target_trading_date: date
    ) -> PipelineRun | None:
        result = await self.db.execute(
            select(PipelineRun)
            .options(selectinload(PipelineRun.steps))
            .where(
                PipelineRun.pipeline_name == pipeline_name,
                PipelineRun.target_trading_date == target_trading_date,
            )
        )
        return result.scalar_one_or_none()

    async def get_run_by_id(self, run_id: int) -> PipelineRun | None:
        result = await self.db.execute(
            select(PipelineRun)
            .options(selectinload(PipelineRun.steps))
            .where(PipelineRun.id == run_id)
        )
        return result.scalar_one_or_none()

    async def get_step(self, run_id: int, step_name: str) -> PipelineRunStep | None:
        result = await self.db.execute(
            select(PipelineRunStep).where(
                PipelineRunStep.run_id == run_id,
                PipelineRunStep.step_name == step_name,
            )
        )
        return result.scalar_one_or_none()
