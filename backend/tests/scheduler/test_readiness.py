"""Trading-calendar and market-provider readiness tests for P10.3."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest

from app.scheduler.readiness import (
    MarketProviderReadinessChecker,
    NSETradingCalendar,
    ReadinessStatus,
    TradingSession,
)
from app.shared.clients.market_data import FundamentalsData, PriceBar

TARGET = date(2026, 8, 5)
OPEN = datetime(2026, 8, 5, 3, 45, tzinfo=timezone.utc)
CLOSE = datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc)
READY_AT = CLOSE + timedelta(hours=1)


def _bar(day: date) -> PriceBar:
    return PriceBar(
        date=day,
        open=100.0,
        high=105.0,
        low=99.0,
        close=104.0,
        volume=1000,
    )


class _Calendar:
    def __init__(self, session: TradingSession | None) -> None:
        self.value = session

    def session(self, _target: date) -> TradingSession | None:
        return self.value


class _Client:
    def __init__(self, bars: list[PriceBar] | None = None) -> None:
        self.bars = bars or []
        self.calls: list[tuple[str, date | None, date | None]] = []

    def fetch_daily_prices(
        self,
        symbol: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[PriceBar]:
        self.calls.append((symbol, start_date, end_date))
        return self.bars

    def fetch_fundamentals(self, _symbol: str) -> FundamentalsData:
        return FundamentalsData()


def _session() -> TradingSession:
    return TradingSession(TARGET, OPEN, CLOSE, READY_AT)


def test_nse_calendar_recognizes_session_weekend_and_republic_day() -> None:
    calendar = NSETradingCalendar(close_grace_minutes=60)

    session = calendar.session(TARGET)
    assert session is not None
    assert session.opens_at == OPEN
    assert session.closes_at == CLOSE
    assert session.data_ready_at == READY_AT
    assert calendar.session(date(2026, 8, 8)) is None  # Saturday
    assert calendar.session(date(2026, 1, 26)) is None  # Republic Day


@pytest.mark.asyncio
async def test_non_trading_day_skips_provider_probe() -> None:
    client = _Client([_bar(TARGET)])
    checker = MarketProviderReadinessChecker(_Calendar(None), client)

    result = await checker.check(TARGET, now=READY_AT)

    assert result.status == ReadinessStatus.NON_TRADING_DAY
    assert client.calls == []


@pytest.mark.asyncio
async def test_too_early_skips_provider_probe() -> None:
    client = _Client([_bar(TARGET)])
    checker = MarketProviderReadinessChecker(_Calendar(_session()), client)

    result = await checker.check(TARGET, now=READY_AT - timedelta(seconds=1))

    assert result.status == ReadinessStatus.TOO_EARLY
    assert result.data_ready_at == READY_AT
    assert client.calls == []


@pytest.mark.asyncio
async def test_provider_is_ready_only_when_target_bar_exists() -> None:
    client = _Client([_bar(TARGET - timedelta(days=1)), _bar(TARGET)])
    checker = MarketProviderReadinessChecker(
        _Calendar(_session()), client, readiness_symbol="^NSEI"
    )

    result = await checker.check(TARGET, now=READY_AT)

    assert result.status == ReadinessStatus.READY
    assert result.ready is True
    assert result.latest_available_date == TARGET
    assert client.calls == [("^NSEI", TARGET, TARGET + timedelta(days=1))]


@pytest.mark.asyncio
async def test_stale_provider_data_is_retryable_not_ready() -> None:
    previous = TARGET - timedelta(days=1)
    checker = MarketProviderReadinessChecker(
        _Calendar(_session()), _Client([_bar(previous)])
    )

    result = await checker.check(TARGET, now=READY_AT)

    assert result.status == ReadinessStatus.DATA_NOT_READY
    assert result.ready is False
    assert result.latest_available_date == previous


@pytest.mark.asyncio
async def test_empty_provider_data_is_not_ready() -> None:
    checker = MarketProviderReadinessChecker(_Calendar(_session()), _Client())

    result = await checker.check(TARGET, now=READY_AT)

    assert result.status == ReadinessStatus.DATA_NOT_READY
    assert result.latest_available_date is None


@pytest.mark.asyncio
async def test_provider_exception_is_sanitized_as_unavailable(caplog) -> None:
    class _FailingClient(_Client):
        def fetch_daily_prices(
            self,
            symbol: str,
            *,
            start_date: date | None = None,
            end_date: date | None = None,
        ) -> list[PriceBar]:
            self.calls.append((symbol, start_date, end_date))
            raise RuntimeError("provider payload secret-token")

    client = _FailingClient()
    checker = MarketProviderReadinessChecker(_Calendar(_session()), client)

    result = await checker.check(TARGET, now=READY_AT)

    assert result.status == ReadinessStatus.PROVIDER_UNAVAILABLE
    assert result.latest_available_date is None
    assert "secret-token" not in caplog.text


@pytest.mark.asyncio
async def test_provider_timeout_is_retryable_unavailable(monkeypatch) -> None:
    async def _never_returns(*_args, **_kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(asyncio, "to_thread", _never_returns)
    checker = MarketProviderReadinessChecker(
        _Calendar(_session()), _Client(), timeout_seconds=0.001
    )

    result = await checker.check(TARGET, now=READY_AT)

    assert result.status == ReadinessStatus.PROVIDER_UNAVAILABLE
