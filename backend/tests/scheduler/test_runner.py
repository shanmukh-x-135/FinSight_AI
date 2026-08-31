"""Tests for the external EOD runner, domain adapters, and advisory lock."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.scheduler import jobs, runner
from app.scheduler.constants import PipelineRunStatus
from app.scheduler.control_plane import StepExecutionError
from app.scheduler.locks import pipeline_run_lock, pipeline_run_lock_id
from app.scheduler.readiness import ReadinessResult, ReadinessStatus

TARGET = date(2026, 8, 5)


@pytest.fixture(autouse=True)
def _ready_preflight(monkeypatch):
    async def _status(_target: date):
        return None

    async def _check(target: date) -> ReadinessResult:
        return ReadinessResult(ReadinessStatus.READY, target)

    monkeypatch.setattr(runner, "get_eod_run_status", _status)
    monkeypatch.setattr(runner, "check_eod_readiness", _check)


@pytest.mark.asyncio
async def test_run_eod_pipeline_calls_control_plane_with_explicit_date(
    monkeypatch,
) -> None:
    calls: list[tuple[str, date]] = []
    expected = SimpleNamespace(
        run_id=7,
        correlation_id="cid",
        status=PipelineRunStatus.COMPLETED,
        acquired=True,
    )

    class _ControlPlane:
        async def execute(self, pipeline_name, target_trading_date):
            calls.append((pipeline_name, target_trading_date))
            return expected

    monkeypatch.setattr(jobs, "build_eod_control_plane", lambda: _ControlPlane())
    result = await jobs.run_eod_pipeline(TARGET)
    assert result is expected
    assert calls == [("eod_market_intelligence", TARGET)]


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

        async def ingest(self, *, target_trading_date):
            assert target_trading_date == TARGET
            return SimpleNamespace(
                requested=2,
                succeeded=["A", "B"],
                failed=[],
                price_bars_fetched=12,
                bootstrap_symbols=0,
                reconciliation_symbols=0,
                incremental_symbols=2,
            )

    class _News:
        def __init__(self, _db):
            pass

        async def ingest(self):
            return SimpleNamespace(
                fetched=5,
                new_articles=3,
                tagged_articles=2,
                articles_reconciled=1,
                tags_added=2,
                tags_removed=1,
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

    assert await jobs._run_market_step(TARGET) == {
        "requested": 2,
        "succeeded": 2,
        "failed": 0,
        "price_bars_fetched": 12,
        "bootstrap_symbols": 0,
        "reconciliation_symbols": 0,
        "incremental_symbols": 2,
    }
    assert await jobs._run_news_step(TARGET) == {
        "fetched": 5,
        "new_articles": 3,
        "tagged_articles": 2,
        "articles_reconciled": 1,
        "tags_added": 2,
        "tags_removed": 1,
        "sentiment_days_updated": 4,
    }
    assert await jobs._run_history_step(TARGET) == {
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

        async def ingest(self, *, target_trading_date):
            assert target_trading_date == TARGET
            return SimpleNamespace(
                requested=2,
                succeeded=["A"],
                failed=["SECRET"],
                price_bars_fetched=6,
                bootstrap_symbols=0,
                reconciliation_symbols=0,
                incremental_symbols=1,
            )

    monkeypatch.setattr(jobs, "SessionFactory", lambda: _Session())
    monkeypatch.setattr(jobs, "MarketIngestionService", _Market)

    with pytest.raises(StepExecutionError) as raised:
        await jobs._run_market_step(TARGET)
    assert raised.value.counters == {
        "requested": 2,
        "succeeded": 1,
        "failed": 1,
        "price_bars_fetched": 6,
        "bootstrap_symbols": 0,
        "reconciliation_symbols": 0,
        "incremental_symbols": 1,
    }
    assert "SECRET" not in raised.value.summary


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (
            SimpleNamespace(
                acquired=True,
                status=PipelineRunStatus.COMPLETED,
                run_id=1,
                correlation_id="cid",
            ),
            runner.EXIT_SUCCESS,
        ),
        (
            SimpleNamespace(
                acquired=False, status=None, run_id=None, correlation_id=None
            ),
            runner.EXIT_SUCCESS,
        ),
        (
            SimpleNamespace(
                acquired=True,
                status=PipelineRunStatus.PARTIAL,
                run_id=1,
                correlation_id="cid",
            ),
            runner.EXIT_PIPELINE_INCOMPLETE,
        ),
        (
            SimpleNamespace(
                acquired=True,
                status=PipelineRunStatus.FAILED,
                run_id=1,
                correlation_id="cid",
            ),
            runner.EXIT_PIPELINE_INCOMPLETE,
        ),
        (
            SimpleNamespace(
                acquired=True,
                status=PipelineRunStatus.RUNNING,
                run_id=1,
                correlation_id="cid",
            ),
            runner.EXIT_PIPELINE_INCOMPLETE,
        ),
    ],
)
@pytest.mark.asyncio
async def test_external_runner_exit_codes_and_engine_cleanup(
    monkeypatch, result, expected
) -> None:
    disposed = 0

    async def _run(_target):
        return result

    async def _dispose():
        nonlocal disposed
        disposed += 1

    monkeypatch.setattr(runner, "run_eod_pipeline", _run)
    monkeypatch.setattr(runner, "dispose_engine", _dispose)

    assert await runner.execute_once(TARGET) == expected
    assert disposed == 1


@pytest.mark.asyncio
async def test_external_runner_maps_unexpected_error_and_disposes_engine(
    monkeypatch,
) -> None:
    disposed = False

    async def _run(_target):
        raise RuntimeError("provider payload with secret")

    async def _dispose():
        nonlocal disposed
        disposed = True

    monkeypatch.setattr(runner, "run_eod_pipeline", _run)
    monkeypatch.setattr(runner, "dispose_engine", _dispose)
    assert await runner.execute_once(TARGET) == runner.EXIT_PIPELINE_INCOMPLETE
    assert disposed is True


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (ReadinessStatus.NON_TRADING_DAY, runner.EXIT_SUCCESS),
        (ReadinessStatus.TOO_EARLY, runner.EXIT_PIPELINE_INCOMPLETE),
        (ReadinessStatus.DATA_NOT_READY, runner.EXIT_PIPELINE_INCOMPLETE),
        (ReadinessStatus.PROVIDER_UNAVAILABLE, runner.EXIT_PIPELINE_INCOMPLETE),
    ],
)
@pytest.mark.asyncio
async def test_readiness_gate_prevents_pipeline_execution(
    monkeypatch, status, expected
) -> None:
    pipeline_called = False

    async def _check(target: date) -> ReadinessResult:
        return ReadinessResult(status, target)

    async def _run(_target):
        nonlocal pipeline_called
        pipeline_called = True

    async def _dispose():
        return None

    monkeypatch.setattr(runner, "check_eod_readiness", _check)
    monkeypatch.setattr(runner, "run_eod_pipeline", _run)
    monkeypatch.setattr(runner, "dispose_engine", _dispose)

    assert await runner.execute_once(TARGET) == expected
    assert pipeline_called is False


@pytest.mark.asyncio
async def test_completed_run_bypasses_provider_preflight_and_pipeline(
    monkeypatch,
) -> None:
    readiness_called = False
    pipeline_called = False

    async def _status(_target: date):
        return PipelineRunStatus.COMPLETED

    async def _check(_target: date):
        nonlocal readiness_called
        readiness_called = True

    async def _run(_target):
        nonlocal pipeline_called
        pipeline_called = True

    async def _dispose():
        return None

    monkeypatch.setattr(runner, "get_eod_run_status", _status)
    monkeypatch.setattr(runner, "check_eod_readiness", _check)
    monkeypatch.setattr(runner, "run_eod_pipeline", _run)
    monkeypatch.setattr(runner, "dispose_engine", _dispose)

    assert await runner.execute_once(TARGET) == runner.EXIT_SUCCESS
    assert readiness_called is False
    assert pipeline_called is False


def test_runner_main_accepts_explicit_target_date(monkeypatch) -> None:
    targets: list[date] = []

    async def _execute(target):
        targets.append(target)
        return runner.EXIT_SUCCESS

    monkeypatch.setattr(runner, "execute_once", _execute)
    assert runner.main(["--target-trading-date", "2026-08-05"]) == 0
    assert targets == [TARGET]


def test_runner_main_resolves_default_target(monkeypatch) -> None:
    called = 0

    async def _execute_default():
        nonlocal called
        called += 1
        return runner.EXIT_SUCCESS

    monkeypatch.setattr(runner, "execute_default_once", _execute_default)
    assert runner.main([]) == 0
    assert called == 1


def test_runner_rejects_invalid_target_date() -> None:
    with pytest.raises(SystemExit) as raised:
        runner.build_parser().parse_args(["--target-trading-date", "05-08-2026"])
    assert raised.value.code == 2


def test_default_date_uses_market_timezone() -> None:
    instant = datetime(2026, 8, 4, 19, 0, tzinfo=timezone.utc)
    assert runner.current_market_date(instant) == TARGET


@pytest.mark.asyncio
async def test_delayed_run_crossing_midnight_resolves_prior_ready_session() -> None:
    friday = date(2026, 8, 7)
    thursday = date(2026, 8, 6)

    class _Calendar:
        def session(self, candidate: date):
            return object() if candidate in {friday, thursday} else None

    async def _check(candidate: date) -> ReadinessResult:
        status = (
            ReadinessStatus.TOO_EARLY if candidate == friday else ReadinessStatus.READY
        )
        return ReadinessResult(status, candidate)

    # 19:30 UTC is 01:00 Friday in the configured Asia/Kolkata market timezone.
    resolved = await runner.resolve_latest_provider_ready_trading_date(
        now=datetime(2026, 8, 6, 19, 30, tzinfo=timezone.utc),
        calendar=_Calendar(),
        readiness_check=_check,
    )
    assert resolved == thursday


@pytest.mark.asyncio
async def test_default_resolution_skips_weekend_and_holiday() -> None:
    friday = date(2026, 8, 7)

    class _Calendar:
        def session(self, candidate: date):
            return object() if candidate == friday else None

    checked: list[date] = []

    async def _check(candidate: date) -> ReadinessResult:
        checked.append(candidate)
        return ReadinessResult(ReadinessStatus.READY, candidate)

    resolved = await runner.resolve_latest_provider_ready_trading_date(
        now=datetime(2026, 8, 9, 6, tzinfo=timezone.utc),
        calendar=_Calendar(),
        readiness_check=_check,
    )
    assert resolved == friday
    assert checked == [friday]


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
    first = pipeline_run_lock_id("eod", TARGET)
    assert first == pipeline_run_lock_id("eod", TARGET)
    assert first != pipeline_run_lock_id("eod", date(2026, 8, 6))
