"""Safety, ordering, failure-boundary, and resume tests for Phase 10D bootstrap."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.history.feature_engineering import FEATURE_VERSION
from app.market.expanded_bootstrap import (
    EXPECTED_DATABASE_REVISION,
    PRODUCTION_CONFIRMATION,
    BootstrapCounts,
    BootstrapSafetyError,
    ExpandedBootstrapService,
)
from app.market.universe_provider import EXPECTED_NIFTY50_COUNT
from config.settings import settings

TARGET = date(2026, 8, 21)
EMPTY = BootstrapCounts(0, 0, 0, 0, 0, 0)
COMPLETE = BootstrapCounts(50, 50, 12500, 11000, 4, 230)


class FakeUniverse:
    def __init__(
        self, *, failures: int = 0, active: int = 50, fallback: bool = False
    ) -> None:
        self.calls = 0
        self.failures = failures
        self.active = active
        self.fallback = fallback

    async def sync(self, **_kwargs: object) -> SimpleNamespace:
        self.calls += 1
        return SimpleNamespace(
            failed_validation_count=self.failures,
            active_count=self.active,
            fallback_used=self.fallback,
            to_payload=lambda: {"active_count": self.active},
        )


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
    assert universe.calls == ingestion.calls == history.calls == 0


@pytest.mark.asyncio
async def test_production_execute_requires_exact_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    service, universe, ingestion, history = _service()

    with pytest.raises(BootstrapSafetyError, match="confirm-production"):
        await service.run(execute=True, target_date=TARGET, production_confirmation="yes")

    assert universe.calls == ingestion.calls == history.calls == 0


@pytest.mark.asyncio
async def test_universe_failure_stops_before_ingestion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "staging")
    service, universe, ingestion, history = _service(FakeUniverse(failures=1))

    with pytest.raises(BootstrapSafetyError, match="Universe validation failed"):
        await service.run(execute=True, target_date=TARGET)

    assert universe.calls == 1
    assert ingestion.calls == history.calls == 0


@pytest.mark.asyncio
async def test_cached_universe_fallback_stops_before_ingestion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "staging")
    service, universe, ingestion, history = _service(FakeUniverse(fallback=True))

    with pytest.raises(BootstrapSafetyError, match="cached snapshot"):
        await service.run(execute=True, target_date=TARGET)

    assert universe.calls == 1
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

    assert universe.calls == ingestion.calls == 1
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
    assert universe.calls == ingestion.calls == history.calls == 2
