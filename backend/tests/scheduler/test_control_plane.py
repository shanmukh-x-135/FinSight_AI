"""Concurrency, recovery, retry, and state tests for the EOD control plane."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.scheduler.constants import (
    PIPELINE_STEP_ORDER,
    PipelineRunStatus,
    PipelineStepName,
    PipelineStepStatus,
)
from app.scheduler.control_plane import EODControlPlane, StepSkipped
from app.scheduler.locks import _local_locks
from app.scheduler.models import PipelineRun, PipelineRunStep
from app.scheduler.repository import PipelineRunRepository
from app.shared.database import Base

TARGET = date(2026, 8, 5)


@pytest_asyncio.fixture
async def session_factory(
    tmp_path,
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'control.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    _local_locks.clear()
    yield factory
    _local_locks.clear()
    await engine.dispose()


def _handlers(calls: list[str]):
    async def market(target: date) -> dict[str, int]:
        assert target == TARGET
        calls.append("market")
        return {"succeeded": 2, "failed": 0}

    async def news(target: date) -> dict[str, int]:
        assert target == TARGET
        calls.append("news")
        return {"new_articles": 3}

    async def history(target: date) -> dict[str, int]:
        assert target == TARGET
        calls.append("history")
        return {"sessions_indexed": 10}

    return {
        PipelineStepName.MARKET: market,
        PipelineStepName.NEWS: news,
        PipelineStepName.HISTORY: history,
    }


@pytest.mark.asyncio
async def test_completed_run_persists_steps_counters_and_correlation_id(
    session_factory,
) -> None:
    calls: list[str] = []
    control = EODControlPlane(session_factory, _handlers(calls))

    result = await control.execute("eod", TARGET)

    assert result.status == PipelineRunStatus.COMPLETED
    assert result.correlation_id
    assert calls == ["market", "news", "history"]
    async with session_factory() as db:
        run = await PipelineRunRepository(db).get_run("eod", TARGET)
        assert run is not None
        assert run.attempt_count == 1
        assert run.counters == {
            "market_succeeded": 2,
            "market_failed": 0,
            "news_new_articles": 3,
            "history_sessions_indexed": 10,
        }
        assert [step.status for step in run.steps] == [
            PipelineStepStatus.COMPLETED,
            PipelineStepStatus.COMPLETED,
            PipelineStepStatus.COMPLETED,
        ]


@pytest.mark.asyncio
async def test_retry_resumes_same_run_skips_success_and_unblocks_downstream(
    session_factory,
) -> None:
    calls: list[str] = []
    news_attempts = 0

    handlers = _handlers(calls)

    async def flaky_news(_target: date) -> dict[str, int]:
        nonlocal news_attempts
        news_attempts += 1
        calls.append("news")
        if news_attempts == 1:
            raise RuntimeError("provider payload secret-token-123")
        return {"new_articles": 4}

    handlers[PipelineStepName.NEWS] = flaky_news
    control = EODControlPlane(session_factory, handlers)

    first = await control.execute("eod", TARGET)
    assert first.status == PipelineRunStatus.PARTIAL
    assert calls == ["market", "news"]

    second = await control.execute("eod", TARGET)
    assert second.run_id == first.run_id
    assert second.correlation_id == first.correlation_id
    assert second.status == PipelineRunStatus.COMPLETED
    assert calls == ["market", "news", "news", "history"]

    async with session_factory() as db:
        run = await PipelineRunRepository(db).get_run("eod", TARGET)
        assert run is not None
        assert run.attempt_count == 2
        assert [step.attempt_count for step in run.steps] == [1, 2, 1]
        persisted = " ".join(
            filter(
                None, [run.last_error_summary, *[s.last_error_summary for s in run.steps]]
            )
        )
        assert "secret-token-123" not in persisted
        assert "provider payload" not in persisted


@pytest.mark.asyncio
async def test_failed_first_step_retries_same_run_and_completed_run_is_noop(
    session_factory,
) -> None:
    calls: list[str] = []
    market_attempts = 0
    handlers = _handlers(calls)

    async def flaky_market(_target: date) -> dict[str, int]:
        nonlocal market_attempts
        market_attempts += 1
        calls.append("market")
        if market_attempts == 1:
            raise RuntimeError("temporary")
        return {"succeeded": 2}

    handlers[PipelineStepName.MARKET] = flaky_market
    control = EODControlPlane(session_factory, handlers)

    failed = await control.execute("eod", TARGET)
    assert failed.status == PipelineRunStatus.FAILED
    completed = await control.execute("eod", TARGET)
    assert completed.run_id == failed.run_id
    assert completed.status == PipelineRunStatus.COMPLETED
    again = await control.execute("eod", TARGET)
    assert again.run_id == failed.run_id
    assert calls == ["market", "market", "news", "history"]

    async with session_factory() as db:
        run = await PipelineRunRepository(db).get_run("eod", TARGET)
        assert run is not None
        assert run.attempt_count == 2
        assert [step.attempt_count for step in run.steps] == [2, 1, 1]


@pytest.mark.asyncio
async def test_concurrent_workers_execute_one_logical_run_once(session_factory) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[str] = []
    handlers = _handlers(calls)

    async def slow_market(_target: date) -> dict[str, int]:
        calls.append("market")
        started.set()
        await release.wait()
        return {"succeeded": 1}

    handlers[PipelineStepName.MARKET] = slow_market
    first_control = EODControlPlane(session_factory, handlers)
    second_control = EODControlPlane(session_factory, handlers)

    first_task = asyncio.create_task(first_control.execute("eod", TARGET))
    await started.wait()
    second = await second_control.execute("eod", TARGET)
    release.set()
    first = await first_task

    assert second.acquired is False
    assert first.status == PipelineRunStatus.COMPLETED
    assert calls == ["market", "news", "history"]
    async with session_factory() as db:
        run = await PipelineRunRepository(db).get_run("eod", TARGET)
        assert run is not None
        assert run.attempt_count == 1


@pytest.mark.asyncio
async def test_stale_run_is_recovered_and_resumed_without_completed_step(
    session_factory,
) -> None:
    stale = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    async with session_factory.begin() as db:
        run = PipelineRun(
            pipeline_name="eod",
            target_trading_date=TARGET,
            correlation_id="1d3e3eb8-c63f-4bdf-a7ed-897547832ee0",
            status=PipelineRunStatus.RUNNING,
            attempt_count=1,
            started_at=stale,
            heartbeat_at=stale,
            counters={"market_succeeded": 2},
        )
        db.add(run)
        await db.flush()
        for sequence, step_name in enumerate(PIPELINE_STEP_ORDER, start=1):
            status = (
                PipelineStepStatus.COMPLETED
                if step_name == PipelineStepName.MARKET
                else PipelineStepStatus.RUNNING
                if step_name == PipelineStepName.NEWS
                else PipelineStepStatus.PENDING
            )
            db.add(
                PipelineRunStep(
                    run_id=run.id,
                    step_name=step_name.value,
                    sequence=sequence,
                    status=status,
                    attempt_count=1 if status != PipelineStepStatus.PENDING else 0,
                    started_at=stale if status != PipelineStepStatus.PENDING else None,
                    heartbeat_at=stale if status != PipelineStepStatus.PENDING else None,
                    counters={"succeeded": 2}
                    if status == PipelineStepStatus.COMPLETED
                    else {},
                )
            )
        stale_run_id = run.id

    calls: list[str] = []
    control = EODControlPlane(
        session_factory,
        _handlers(calls),
        stale_after=timedelta(minutes=5),
    )
    result = await control.execute("eod", TARGET)

    assert result.run_id == stale_run_id
    assert result.status == PipelineRunStatus.COMPLETED
    assert calls == ["news", "history"]
    async with session_factory() as db:
        recovered = await PipelineRunRepository(db).get_run("eod", TARGET)
        assert recovered is not None
        assert recovered.attempt_count == 2
        assert [step.attempt_count for step in recovered.steps] == [1, 2, 1]


@pytest.mark.asyncio
async def test_recent_running_run_is_not_recovered(session_factory) -> None:
    now = datetime.now(tz=timezone.utc)
    async with session_factory.begin() as db:
        run = PipelineRun(
            pipeline_name="eod",
            target_trading_date=TARGET,
            correlation_id="fe9bf113-34f8-4473-98c2-8ae7573877f4",
            status=PipelineRunStatus.RUNNING,
            attempt_count=1,
            started_at=now,
            heartbeat_at=now,
            counters={},
        )
        db.add(run)
        await db.flush()
        for sequence, step_name in enumerate(PIPELINE_STEP_ORDER, start=1):
            db.add(
                PipelineRunStep(
                    run_id=run.id,
                    step_name=step_name.value,
                    sequence=sequence,
                    status=PipelineStepStatus.PENDING,
                    counters={},
                )
            )

    calls: list[str] = []
    result = await EODControlPlane(
        session_factory, _handlers(calls), stale_after=timedelta(minutes=5)
    ).execute("eod", TARGET)
    assert result.status == PipelineRunStatus.RUNNING
    assert calls == []


@pytest.mark.asyncio
async def test_heartbeat_advances_while_step_runs(session_factory) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    handlers = _handlers([])

    async def waiting_market(_target: date) -> dict[str, int]:
        started.set()
        await release.wait()
        return {"succeeded": 1}

    handlers[PipelineStepName.MARKET] = waiting_market
    control = EODControlPlane(session_factory, handlers, heartbeat_interval_seconds=0.02)
    task = asyncio.create_task(control.execute("eod", TARGET))
    await started.wait()
    async with session_factory() as db:
        before = await PipelineRunRepository(db).get_run("eod", TARGET)
        assert before is not None and before.heartbeat_at is not None
        first_heartbeat = before.heartbeat_at
    await asyncio.sleep(0.06)
    async with session_factory() as db:
        after = await PipelineRunRepository(db).get_run("eod", TARGET)
        assert after is not None and after.heartbeat_at is not None
        assert after.heartbeat_at > first_heartbeat
    release.set()
    await task


@pytest.mark.asyncio
async def test_intentional_step_skip_is_terminal_and_allows_downstream(
    session_factory,
) -> None:
    calls: list[str] = []
    handlers = _handlers(calls)

    async def skipped_news(_target: date) -> dict[str, int]:
        calls.append("news")
        raise StepSkipped({"reason_code": 1})

    handlers[PipelineStepName.NEWS] = skipped_news
    result = await EODControlPlane(session_factory, handlers).execute("eod", TARGET)
    assert result.status == PipelineRunStatus.COMPLETED
    assert calls == ["market", "news", "history"]
    async with session_factory() as db:
        run = await PipelineRunRepository(db).get_run("eod", TARGET)
        assert run is not None
        assert run.steps[1].status == PipelineStepStatus.SKIPPED
