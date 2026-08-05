"""PostgreSQL integration coverage for cross-connection advisory locking."""

from __future__ import annotations

import asyncio
import os
from datetime import date

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.scheduler.constants import PipelineRunStatus, PipelineStepName
from app.scheduler.control_plane import EODControlPlane
from app.scheduler.models import PipelineRun, PipelineRunStep

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL, reason="TEST_POSTGRES_URL is required for PostgreSQL integration"
)


@pytest.mark.asyncio
async def test_postgres_advisory_lock_allows_only_one_worker() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_size=5)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    pipeline_name = "postgres_concurrency_test"
    target = date(2099, 1, 7)
    async with factory.begin() as db:
        run_ids = select(PipelineRun.id).where(PipelineRun.pipeline_name == pipeline_name)
        await db.execute(
            delete(PipelineRunStep).where(PipelineRunStep.run_id.in_(run_ids))
        )
        await db.execute(
            delete(PipelineRun).where(PipelineRun.pipeline_name == pipeline_name)
        )

    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[str] = []

    async def market(_target: date) -> dict[str, int]:
        calls.append("market")
        started.set()
        await release.wait()
        return {"succeeded": 1}

    async def news(_target: date) -> dict[str, int]:
        calls.append("news")
        return {"new_articles": 1}

    async def history(_target: date) -> dict[str, int]:
        calls.append("history")
        return {"sessions_indexed": 1}

    handlers = {
        PipelineStepName.MARKET: market,
        PipelineStepName.NEWS: news,
        PipelineStepName.HISTORY: history,
    }
    try:
        first_task = asyncio.create_task(
            EODControlPlane(factory, handlers).execute(pipeline_name, target)
        )
        await started.wait()
        second = await EODControlPlane(factory, handlers).execute(pipeline_name, target)
        release.set()
        first = await first_task

        assert second.acquired is False
        assert first.status == PipelineRunStatus.COMPLETED
        assert calls == ["market", "news", "history"]
        async with factory() as db:
            count = await db.scalar(
                select(func.count(PipelineRun.id)).where(
                    PipelineRun.pipeline_name == pipeline_name,
                    PipelineRun.target_trading_date == target,
                )
            )
            assert count == 1
    finally:
        async with factory.begin() as db:
            run_ids = select(PipelineRun.id).where(
                PipelineRun.pipeline_name == pipeline_name
            )
            await db.execute(
                delete(PipelineRunStep).where(PipelineRunStep.run_id.in_(run_ids))
            )
            await db.execute(
                delete(PipelineRun).where(PipelineRun.pipeline_name == pipeline_name)
            )
        await engine.dispose()
