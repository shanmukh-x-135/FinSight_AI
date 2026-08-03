"""Tests for the scheduler lifecycle and the ingestion job wiring."""

from __future__ import annotations

import pytest

from app.market.schemas import IngestionResult
from app.scheduler import jobs, scheduler
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
