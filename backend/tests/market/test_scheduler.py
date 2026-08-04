"""Tests for the scheduler lifecycle and the ingestion job wiring."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.market.schemas import IngestionResult
from app.scheduler import jobs, scheduler
from app.scheduler.locks import scheduler_job_lock
from config.settings import settings


@pytest.mark.asyncio
async def test_start_scheduler_registers_job_then_stops() -> None:
    scheduler.start_scheduler()
    try:
        assert scheduler._scheduler is not None
        assert scheduler._scheduler.running
        job = scheduler._scheduler.get_job(scheduler.MARKET_INGESTION_JOB_ID)
        assert job is not None
    finally:
        scheduler.shutdown_scheduler()
    assert scheduler._scheduler is None


@pytest.mark.asyncio
async def test_scheduler_respects_disabled_flag(monkeypatch) -> None:
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    scheduler.shutdown_scheduler()  # ensure clean slate
    scheduler.start_scheduler()
    assert scheduler._scheduler is None


@pytest.mark.asyncio
async def test_market_ingestion_job_runs(monkeypatch) -> None:
    ran = {"ingest": False}

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    class _FakeService:
        def __init__(self, _db):
            pass

        async def ingest(self, symbols=None):
            ran["ingest"] = True
            return IngestionResult(requested=1, succeeded=["X.NS"], failed=[])

    monkeypatch.setattr(jobs, "SessionFactory", lambda: _FakeSession())
    monkeypatch.setattr(jobs, "MarketIngestionService", _FakeService)

    await jobs.market_ingestion_job()
    assert ran["ingest"] is True


@pytest.mark.asyncio
async def test_concurrent_scheduler_workers_run_pipeline_once(monkeypatch) -> None:
    """A second worker skips immediately while the first owns the job lock."""
    started = asyncio.Event()
    release = asyncio.Event()
    calls = {"market": 0, "news": 0, "history": 0}

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    class _Market:
        def __init__(self, _db):
            pass

        async def ingest(self, symbols=None):
            calls["market"] += 1
            started.set()
            await release.wait()
            return IngestionResult(requested=1, succeeded=["X.NS"], failed=[])

    class _News:
        def __init__(self, _db):
            pass

        async def ingest(self):
            calls["news"] += 1
            return SimpleNamespace(new_articles=1, tagged_articles=1)

    class _History:
        def __init__(self, _db):
            pass

        async def build_index(self):
            calls["history"] += 1
            return SimpleNamespace(sessions_indexed=1)

    monkeypatch.setattr(jobs, "SessionFactory", lambda: _FakeSession())
    monkeypatch.setattr(jobs, "MarketIngestionService", _Market)
    monkeypatch.setattr(jobs, "NewsService", _News)
    monkeypatch.setattr(jobs, "HistoryService", _History)

    first = asyncio.create_task(jobs.market_ingestion_job())
    await started.wait()
    await jobs.market_ingestion_job()
    release.set()
    await first

    assert calls == {"market": 1, "news": 1, "history": 1}


@pytest.mark.asyncio
async def test_postgres_scheduler_lock_is_acquired_and_released() -> None:
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

    async with scheduler_job_lock(_PostgresSession(), 42) as acquired:
        assert acquired is True

    assert statements == [
        ("SELECT pg_try_advisory_lock(:lock_id)", {"lock_id": 42}),
        ("SELECT pg_advisory_unlock(:lock_id)", {"lock_id": 42}),
    ]
