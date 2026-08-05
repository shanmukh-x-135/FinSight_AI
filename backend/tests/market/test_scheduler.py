"""Tests for scheduler lifecycle and thin EOD caller wiring."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.scheduler import jobs, scheduler
from app.scheduler.constants import PipelineRunStatus
from app.scheduler.control_plane import StepExecutionError
from app.scheduler.locks import pipeline_run_lock, pipeline_run_lock_id
from config.settings import settings


@pytest.mark.asyncio
async def test_start_scheduler_registers_job_then_stops() -> None:
    scheduler.start_scheduler()
    try:
        assert scheduler._scheduler is not None
        assert scheduler._scheduler.running
        assert scheduler._scheduler.get_job(scheduler.MARKET_INGESTION_JOB_ID) is not None
    finally:
        scheduler.shutdown_scheduler()
    assert scheduler._scheduler is None


def test_scheduler_respects_disabled_flag(monkeypatch) -> None:
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    scheduler.shutdown_scheduler()
    scheduler.start_scheduler()
    assert scheduler._scheduler is None


@pytest.mark.asyncio
async def test_market_ingestion_job_is_thin_control_plane_caller(monkeypatch) -> None:
    target = date(2026, 8, 5)
    calls: list[tuple[str, date]] = []

    class _ControlPlane:
        async def execute(self, pipeline_name, target_trading_date):
            calls.append((pipeline_name, target_trading_date))
            return SimpleNamespace(
                run_id=7,
                correlation_id="cid",
                status=PipelineRunStatus.COMPLETED,
                acquired=True,
            )

    monkeypatch.setattr(jobs, "build_eod_control_plane", lambda: _ControlPlane())
    await jobs.market_ingestion_job(target)
    assert calls == [("eod_market_intelligence", target)]


@pytest.mark.asyncio
async def test_domain_step_adapters_return_only_numeric_counters(monkeypatch) -> None:
    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    class _Market:
        def __init__(self, _db):
            pass

        async def ingest(self):
            return SimpleNamespace(requested=2, succeeded=["A", "B"], failed=[])

    class _News:
        def __init__(self, _db):
            pass

        async def ingest(self):
            return SimpleNamespace(
                fetched=5,
                new_articles=3,
                tagged_articles=2,
                sentiment_days_updated=4,
            )

    class _History:
        def __init__(self, _db):
            pass

        async def build_index(self):
            return SimpleNamespace(sessions_indexed=20, dim=11)

    monkeypatch.setattr(jobs, "SessionFactory", lambda: _Session())
    monkeypatch.setattr(jobs, "MarketIngestionService", _Market)
    monkeypatch.setattr(jobs, "NewsService", _News)
    monkeypatch.setattr(jobs, "HistoryService", _History)

    assert await jobs._run_market_step(date(2026, 8, 5)) == {
        "requested": 2,
        "succeeded": 2,
        "failed": 0,
    }
    assert await jobs._run_news_step(date(2026, 8, 5)) == {
        "fetched": 5,
        "new_articles": 3,
        "tagged_articles": 2,
        "sentiment_days_updated": 4,
    }
    assert await jobs._run_history_step(date(2026, 8, 5)) == {
        "sessions_indexed": 20,
        "dimension": 11,
    }


@pytest.mark.asyncio
async def test_market_adapter_promotes_partial_batch_to_retryable_failure(
    monkeypatch,
) -> None:
    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    class _Market:
        def __init__(self, _db):
            pass

        async def ingest(self):
            return SimpleNamespace(requested=2, succeeded=["A"], failed=["SECRET"])

    monkeypatch.setattr(jobs, "SessionFactory", lambda: _Session())
    monkeypatch.setattr(jobs, "MarketIngestionService", _Market)

    with pytest.raises(StepExecutionError) as raised:
        await jobs._run_market_step(date(2026, 8, 5))
    assert raised.value.counters == {"requested": 2, "succeeded": 1, "failed": 1}
    assert "SECRET" not in raised.value.summary


@pytest.mark.asyncio
async def test_postgres_pipeline_lock_is_acquired_and_released() -> None:
    statements: list[tuple[str, dict]] = []

    class _Result:
        def scalar(self):
            return True

    class _PostgresSession:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        async def execute(self, statement, params):
            statements.append((str(statement), params))
            return _Result()

    async with pipeline_run_lock(_PostgresSession(), 42) as acquired:
        assert acquired is True

    assert statements == [
        ("SELECT pg_try_advisory_lock(:lock_id)", {"lock_id": 42}),
        ("SELECT pg_advisory_unlock(:lock_id)", {"lock_id": 42}),
    ]


def test_pipeline_lock_id_is_stable_and_scoped_to_target_date() -> None:
    first = pipeline_run_lock_id("eod", date(2026, 8, 5))
    assert first == pipeline_run_lock_id("eod", date(2026, 8, 5))
    assert first != pipeline_run_lock_id("eod", date(2026, 8, 6))
