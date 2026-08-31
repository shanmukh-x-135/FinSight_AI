"""Durable, resumable execution control for the EOD pipeline."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TypeAlias
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.scheduler.constants import (
    PIPELINE_STEP_ORDER,
    PipelineRunStatus,
    PipelineStepName,
    PipelineStepStatus,
)
from app.scheduler.locks import pipeline_run_lock, pipeline_run_lock_id
from app.scheduler.models import PipelineRun, PipelineRunStep
from app.scheduler.repository import PipelineRunRepository
from app.shared.time import as_utc, utc_now
from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)

CounterMap: TypeAlias = dict[str, int]
StepHandler: TypeAlias = Callable[[date], Awaitable[CounterMap]]


@dataclass(frozen=True)
class PipelineExecutionResult:
    run_id: int | None
    correlation_id: str | None
    status: PipelineRunStatus | None
    acquired: bool


class StepExecutionError(RuntimeError):
    """A safe-to-persist step failure with optional non-sensitive counters."""

    def __init__(self, summary: str, counters: CounterMap | None = None) -> None:
        super().__init__(summary)
        self.summary = summary[:500]
        self.counters = counters or {}


class StepSkipped(RuntimeError):
    """Signal that a step is intentionally satisfied without executing work."""

    def __init__(self, counters: CounterMap | None = None) -> None:
        super().__init__("Step skipped")
        self.counters = counters or {}


def sanitized_error_summary(exc: BaseException) -> str:
    """Return a bounded error class summary without payloads or traceback text."""
    if isinstance(exc, StepExecutionError):
        return exc.summary
    return f"Step execution failed ({type(exc).__name__})"[:500]


class EODControlPlane:
    """Run the ordered EOD steps with durable checkpoints and retry semantics."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        handlers: Mapping[PipelineStepName, StepHandler],
        *,
        stale_after: timedelta | None = None,
        heartbeat_interval_seconds: float | None = None,
    ) -> None:
        missing = set(PIPELINE_STEP_ORDER) - set(handlers)
        if missing:
            raise ValueError(f"Missing pipeline handlers: {sorted(missing)}")
        self.session_factory = session_factory
        self.handlers = handlers
        self.stale_after = stale_after or timedelta(
            seconds=settings.pipeline_stale_after_seconds
        )
        self.heartbeat_interval_seconds = (
            heartbeat_interval_seconds
            if heartbeat_interval_seconds is not None
            else settings.pipeline_heartbeat_interval_seconds
        )

    async def execute(
        self, pipeline_name: str, target_trading_date: date
    ) -> PipelineExecutionResult:
        """Start or resume the one logical run for the supplied trading date."""
        lock_id = pipeline_run_lock_id(pipeline_name, target_trading_date)
        async with self.session_factory() as lock_db:
            async with pipeline_run_lock(lock_db, lock_id) as acquired:
                if not acquired:
                    logger.info(
                        "pipeline_run_skipped_lock_held",
                        extra={
                            "pipeline_name": pipeline_name,
                            "target_trading_date": target_trading_date.isoformat(),
                        },
                    )
                    return PipelineExecutionResult(None, None, None, False)

                run = await self._start_or_resume(pipeline_name, target_trading_date)
                if run.status == PipelineRunStatus.COMPLETED:
                    return self._result(run, acquired=True)
                if run.status == PipelineRunStatus.RUNNING:
                    # A recent heartbeat is not stolen even if the lock connection was
                    # interrupted momentarily; only stale executions are recoverable.
                    return self._result(run, acquired=True)

                run = await self._mark_run_started(run.id)
                for step_name in PIPELINE_STEP_ORDER:
                    step = next(step for step in run.steps if step.step_name == step_name)
                    if step.status in {
                        PipelineStepStatus.COMPLETED,
                        PipelineStepStatus.SKIPPED,
                    }:
                        logger.info(
                            "pipeline_step_resume_skip",
                            extra={
                                "correlation_id": run.correlation_id,
                                "step": step_name.value,
                            },
                        )
                        continue

                    await self._mark_step_started(run.id, step_name)
                    try:
                        counters = await self._run_with_heartbeat(
                            run.id,
                            step_name,
                            self.handlers[step_name],
                            target_trading_date,
                        )
                    except StepSkipped as exc:
                        run = await self._mark_step_skipped(
                            run.id, step_name, exc.counters
                        )
                        continue
                    except Exception as exc:  # noqa: BLE001 - persisted safely below
                        counters = (
                            exc.counters if isinstance(exc, StepExecutionError) else {}
                        )
                        summary = sanitized_error_summary(exc)
                        run = await self._mark_step_failed(
                            run.id, step_name, summary, counters
                        )
                        logger.error(
                            "pipeline_step_failed",
                            extra={
                                "correlation_id": run.correlation_id,
                                "step": step_name.value,
                                "error": type(exc).__name__,
                            },
                        )
                        return self._result(run, acquired=True)

                    run = await self._mark_step_completed(run.id, step_name, counters)

                run = await self._mark_run_completed(run.id)
                return self._result(run, acquired=True)

    async def _start_or_resume(
        self, pipeline_name: str, target_trading_date: date
    ) -> PipelineRun:
        async with self.session_factory.begin() as db:
            repo = PipelineRunRepository(db)
            run = await repo.get_run(pipeline_name, target_trading_date)
            now = utc_now()
            if run is None:
                run = PipelineRun(
                    pipeline_name=pipeline_name,
                    target_trading_date=target_trading_date,
                    correlation_id=str(uuid4()),
                    status=PipelineRunStatus.PENDING,
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
                await db.flush()
                run = await repo.get_run_by_id(run.id)
                assert run is not None
                return run

            if run.status == PipelineRunStatus.RUNNING:
                heartbeat = run.heartbeat_at or run.started_at or run.created_at
                if now - as_utc(heartbeat) > self.stale_after:
                    for step in run.steps:
                        if step.status == PipelineStepStatus.RUNNING:
                            step.status = PipelineStepStatus.FAILED
                            step.last_error_summary = "Recovered after stale execution"
                            step.completed_at = now
                    completed = any(
                        step.status == PipelineStepStatus.COMPLETED for step in run.steps
                    )
                    run.status = (
                        PipelineRunStatus.PARTIAL
                        if completed
                        else PipelineRunStatus.FAILED
                    )
                    run.last_error_summary = "Recovered after stale execution"
                    run.completed_at = now
                    run.heartbeat_at = now
                return run
            return run

    async def _mark_run_started(self, run_id: int) -> PipelineRun:
        async with self.session_factory.begin() as db:
            run = await PipelineRunRepository(db).get_run_by_id(run_id)
            assert run is not None
            now = utc_now()
            run.status = PipelineRunStatus.RUNNING
            run.attempt_count += 1
            run.started_at = now
            run.heartbeat_at = now
            run.completed_at = None
            run.last_error_summary = None
            return run

    async def _mark_step_started(self, run_id: int, step_name: PipelineStepName) -> None:
        async with self.session_factory.begin() as db:
            repo = PipelineRunRepository(db)
            run = await repo.get_run_by_id(run_id)
            step = await repo.get_step(run_id, step_name.value)
            assert run is not None and step is not None
            now = utc_now()
            step.status = PipelineStepStatus.RUNNING
            step.attempt_count += 1
            step.started_at = now
            step.heartbeat_at = now
            step.completed_at = None
            step.last_error_summary = None
            run.heartbeat_at = now

    async def _heartbeat(self, run_id: int, step_name: PipelineStepName) -> None:
        async with self.session_factory.begin() as db:
            repo = PipelineRunRepository(db)
            run = await repo.get_run_by_id(run_id)
            step = await repo.get_step(run_id, step_name.value)
            if run is None or step is None:
                return
            now = utc_now()
            run.heartbeat_at = now
            step.heartbeat_at = now

    async def _run_with_heartbeat(
        self,
        run_id: int,
        step_name: PipelineStepName,
        handler: StepHandler,
        target_trading_date: date,
    ) -> CounterMap:
        task = asyncio.create_task(handler(target_trading_date))
        try:
            while True:
                done, _ = await asyncio.wait(
                    {task}, timeout=self.heartbeat_interval_seconds
                )
                if task in done:
                    return await task
                await self._heartbeat(run_id, step_name)
        except BaseException:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            raise

    async def _mark_step_completed(
        self, run_id: int, step_name: PipelineStepName, counters: CounterMap
    ) -> PipelineRun:
        async with self.session_factory.begin() as db:
            repo = PipelineRunRepository(db)
            run = await repo.get_run_by_id(run_id)
            step = await repo.get_step(run_id, step_name.value)
            assert run is not None and step is not None
            now = utc_now()
            step.status = PipelineStepStatus.COMPLETED
            step.counters = dict(counters)
            step.completed_at = now
            step.heartbeat_at = now
            step.last_error_summary = None
            run.counters = self._combined_counters(run)
            run.heartbeat_at = now
            return run

    async def _mark_step_failed(
        self,
        run_id: int,
        step_name: PipelineStepName,
        summary: str,
        counters: CounterMap,
    ) -> PipelineRun:
        async with self.session_factory.begin() as db:
            repo = PipelineRunRepository(db)
            run = await repo.get_run_by_id(run_id)
            step = await repo.get_step(run_id, step_name.value)
            assert run is not None and step is not None
            now = utc_now()
            step.status = PipelineStepStatus.FAILED
            step.counters = dict(counters)
            step.last_error_summary = summary
            step.completed_at = now
            step.heartbeat_at = now
            completed = any(
                candidate.status == PipelineStepStatus.COMPLETED
                for candidate in run.steps
            )
            run.status = (
                PipelineRunStatus.PARTIAL if completed else PipelineRunStatus.FAILED
            )
            run.counters = self._combined_counters(run)
            run.last_error_summary = summary
            run.completed_at = now
            run.heartbeat_at = now
            return run

    async def _mark_step_skipped(
        self, run_id: int, step_name: PipelineStepName, counters: CounterMap
    ) -> PipelineRun:
        async with self.session_factory.begin() as db:
            repo = PipelineRunRepository(db)
            run = await repo.get_run_by_id(run_id)
            step = await repo.get_step(run_id, step_name.value)
            assert run is not None and step is not None
            now = utc_now()
            step.status = PipelineStepStatus.SKIPPED
            step.counters = dict(counters)
            step.completed_at = now
            step.heartbeat_at = now
            step.last_error_summary = None
            run.counters = self._combined_counters(run)
            run.heartbeat_at = now
            return run

    async def _mark_run_completed(self, run_id: int) -> PipelineRun:
        async with self.session_factory.begin() as db:
            run = await PipelineRunRepository(db).get_run_by_id(run_id)
            assert run is not None
            now = utc_now()
            run.status = PipelineRunStatus.COMPLETED
            run.counters = self._combined_counters(run)
            run.last_error_summary = None
            run.completed_at = now
            run.heartbeat_at = now
            return run

    @staticmethod
    def _combined_counters(run: PipelineRun) -> CounterMap:
        combined: CounterMap = {}
        for step in run.steps:
            for key, value in step.counters.items():
                combined[f"{step.step_name}_{key}"] = value
        return combined

    @staticmethod
    def _result(run: PipelineRun, *, acquired: bool) -> PipelineExecutionResult:
        return PipelineExecutionResult(
            run_id=run.id,
            correlation_id=run.correlation_id,
            status=run.status,
            acquired=acquired,
        )
