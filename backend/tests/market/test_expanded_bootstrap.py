"""Safety, ordering, failure-boundary, and resume tests for Phase 10D bootstrap."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.history.feature_engineering import FEATURE_VERSION
from app.market.expanded_bootstrap import (
    EXPECTED_DATABASE_REVISION,
    PRODUCTION_CONFIRMATION,
    BootstrapCounts,
    BootstrapSafetyError,
    ExpandedBootstrapService,
)
from app.market.models import UniverseSyncRun
from app.market.universe_provider import EXPECTED_NIFTY50_COUNT
from app.scheduler.constants import EOD_PIPELINE_NAME, PipelineRunStatus
from app.scheduler.models import PipelineRun
from config.settings import settings

TARGET = date(2026, 8, 21)
EMPTY = BootstrapCounts(0, 0, 0, 0, 0, 0)
COMPLETE = BootstrapCounts(50, 50, 12500, 11000, 4, 230)


class FakeUniverse:
    def __init__(
        self,
        *,
        failures: int = 0,
        active: int = 50,
        fallback: bool = False,
        fetched: int = 50,
        normalized: int = 50,
    ) -> None:
        self.calls = 0
        self.preflight_calls = 0
        self.failures = failures
        self.active = active
        self.fallback = fallback
        self.fetched = fetched
        self.normalized = normalized

    def _result(self, *, dry_run: bool) -> SimpleNamespace:
        return SimpleNamespace(
            failed_validation_count=self.failures,
            active_count=self.active,
            fallback_used=self.fallback,
            fetched_count=self.fetched,
            normalized_count=self.normalized,
            validated_count=self.normalized - self.failures,
            to_payload=lambda: {
                "fetched_count": self.fetched,
                "normalized_count": self.normalized,
                "validated_count": self.normalized - self.failures,
                "failed_validation_count": self.failures,
                "active_count": self.active,
                "dry_run": dry_run,
            },
        )

    async def preflight(self, **_kwargs: object) -> SimpleNamespace:
        self.preflight_calls += 1
        return self._result(dry_run=True)

    async def sync(self, **_kwargs: object) -> SimpleNamespace:
        self.calls += 1
        return self._result(dry_run=False)


class FakeIngestion:
    def __init__(self, *, failed: list[str] | None = None, requested: int = 54) -> None:
        self.calls = 0
        self.failed = failed or []
        self.requested = requested

    async def ingest(self, **_kwargs: object) -> SimpleNamespace:
        self.calls += 1
        return SimpleNamespace(
            failed=self.failed,
            requested=self.requested,
            model_dump=lambda **_kwargs: {
                "requested": self.requested,
                "failed": self.failed,
            },
        )


class FakeHistory:
    def __init__(self) -> None:
        self.calls = 0

    async def build_index(self) -> SimpleNamespace:
        self.calls += 1
        return SimpleNamespace(
            feature_version=FEATURE_VERSION,
            model_dump=lambda **_kwargs: {
                "feature_version": FEATURE_VERSION,
                "sessions_indexed": 230,
            },
        )


def _service(
    universe: FakeUniverse | None = None,
    ingestion: FakeIngestion | None = None,
    history: FakeHistory | None = None,
) -> tuple[ExpandedBootstrapService, FakeUniverse, FakeIngestion, FakeHistory]:
    universe = universe or FakeUniverse()
    ingestion = ingestion or FakeIngestion()
    history = history or FakeHistory()
    service = ExpandedBootstrapService(
        AsyncMock(),  # type: ignore[arg-type]
        universe_service=universe,  # type: ignore[arg-type]
        ingestion_service=ingestion,  # type: ignore[arg-type]
        history_service=history,  # type: ignore[arg-type]
    )
    service._verify_database_revision = AsyncMock(  # type: ignore[method-assign]
        return_value=EXPECTED_DATABASE_REVISION
    )
    service._counts = AsyncMock(side_effect=[EMPTY, COMPLETE])  # type: ignore[method-assign]
    service._verify_no_conflicting_jobs = AsyncMock(  # type: ignore[method-assign]
        return_value=()
    )
    return service, universe, ingestion, history


@pytest.mark.asyncio
async def test_preflight_is_read_only_and_reports_production_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    service, universe, ingestion, history = _service()

    result = await service.run(execute=False, target_date=TARGET)

    assert result.status == "preflight_ready"
    assert result.production_confirmation_required == PRODUCTION_CONFIRMATION
    assert result.universe == {
        "fetched_count": 50,
        "normalized_count": 50,
        "validated_count": 50,
        "failed_validation_count": 0,
        "active_count": 50,
        "dry_run": True,
    }
    assert universe.preflight_calls == 1
    assert universe.calls == ingestion.calls == history.calls == 0


@pytest.mark.asyncio
async def test_production_execute_requires_exact_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    service, universe, ingestion, history = _service()

    with pytest.raises(BootstrapSafetyError, match="confirm-production"):
        await service.run(execute=True, target_date=TARGET, production_confirmation="yes")

    assert universe.preflight_calls == 0
    assert universe.calls == ingestion.calls == history.calls == 0


@pytest.mark.asyncio
async def test_universe_failure_stops_before_ingestion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "staging")
    service, universe, ingestion, history = _service(FakeUniverse(failures=1))

    with pytest.raises(BootstrapSafetyError, match="Universe validation failed"):
        await service.run(execute=True, target_date=TARGET)

    assert universe.preflight_calls == 1
    assert universe.calls == 0
    assert ingestion.calls == history.calls == 0


@pytest.mark.asyncio
async def test_cached_universe_fallback_stops_before_ingestion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "staging")
    service, universe, ingestion, history = _service(FakeUniverse(fallback=True))

    with pytest.raises(BootstrapSafetyError, match="cached snapshot"):
        await service.run(execute=True, target_date=TARGET)

    assert universe.preflight_calls == 1
    assert universe.calls == 0
    assert ingestion.calls == history.calls == 0


@pytest.mark.asyncio
async def test_ingestion_failure_is_resumable_and_stops_before_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "staging")
    service, universe, ingestion, history = _service(
        ingestion=FakeIngestion(failed=["INFY.NS"])
    )

    with pytest.raises(BootstrapSafetyError, match="INFY.NS"):
        await service.run(execute=True, target_date=TARGET)

    assert universe.preflight_calls == universe.calls == ingestion.calls == 1
    assert history.calls == 0


@pytest.mark.asyncio
async def test_complete_workflow_can_be_safely_repeated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "staging")
    service, universe, ingestion, history = _service()
    service._counts = AsyncMock(  # type: ignore[method-assign]
        side_effect=[EMPTY, COMPLETE, COMPLETE, COMPLETE]
    )

    first = await service.run(execute=True, target_date=TARGET)
    second = await service.run(execute=True, target_date=TARGET)

    assert first.status == second.status == "completed"
    assert first.after.active_constituents == EXPECTED_NIFTY50_COUNT
    assert universe.preflight_calls == 2
    assert universe.calls == ingestion.calls == history.calls == 2


@pytest.mark.asyncio
async def test_preflight_rejects_incomplete_official_universe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    service, universe, ingestion, history = _service(
        FakeUniverse(fetched=49, normalized=49, active=49)
    )

    with pytest.raises(BootstrapSafetyError, match="50 fetched"):
        await service.run(execute=False, target_date=TARGET)

    assert universe.preflight_calls == 1
    assert universe.calls == ingestion.calls == history.calls == 0


@pytest.mark.asyncio
async def test_conflicting_job_stops_before_external_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    service, universe, ingestion, history = _service()
    service._verify_no_conflicting_jobs = AsyncMock(  # type: ignore[method-assign]
        side_effect=BootstrapSafetyError("Conflicting production operation is active")
    )

    with pytest.raises(BootstrapSafetyError, match="Conflicting production operation"):
        await service.run(execute=False, target_date=TARGET)

    assert universe.preflight_calls == 0
    assert universe.calls == ingestion.calls == history.calls == 0


@pytest.mark.asyncio
async def test_recent_eod_and_universe_runs_are_reported_as_conflicts(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(tz=timezone.utc)
    eod = PipelineRun(
        pipeline_name=EOD_PIPELINE_NAME,
        target_trading_date=TARGET,
        correlation_id="phase-10d-conflict",
        status=PipelineRunStatus.RUNNING,
        counters={},
        heartbeat_at=now,
    )
    universe = UniverseSyncRun(
        index_code="NIFTY50",
        source="test",
        status="running",
        dry_run=False,
        started_at=now,
    )
    db_session.add_all([eod, universe])
    await db_session.commit()

    with pytest.raises(BootstrapSafetyError, match="eod:.*universe-sync"):
        await ExpandedBootstrapService(db_session)._verify_no_conflicting_jobs()


@pytest.mark.asyncio
async def test_stale_job_state_does_not_block_operator_preflight(
    db_session: AsyncSession,
) -> None:
    stale = datetime.now(tz=timezone.utc) - timedelta(
        seconds=settings.pipeline_stale_after_seconds + 1
    )
    db_session.add(
        PipelineRun(
            pipeline_name=EOD_PIPELINE_NAME,
            target_trading_date=TARGET,
            correlation_id="phase-10d-stale",
            status=PipelineRunStatus.RUNNING,
            counters={},
            heartbeat_at=stale,
        )
    )
    await db_session.commit()

    assert await ExpandedBootstrapService(db_session)._verify_no_conflicting_jobs() == ()
