"""NSE trading-session and market-provider readiness checks for EOD execution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Protocol

import pandas_market_calendars as market_calendars

from app.shared.clients.market_data import MarketDataClient
from app.shared.clients.yfinance_client import build_default_client
from app.shared.time import as_utc, utc_now
from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)


class ReadinessStatus(StrEnum):
    """Stable, non-sensitive outcomes from the EOD preflight."""

    READY = "ready"
    NON_TRADING_DAY = "non_trading_day"
    TOO_EARLY = "too_early"
    DATA_NOT_READY = "data_not_ready"
    PROVIDER_UNAVAILABLE = "provider_unavailable"


@dataclass(frozen=True)
class TradingSession:
    trading_date: date
    opens_at: datetime
    closes_at: datetime
    data_ready_at: datetime


@dataclass(frozen=True)
class ReadinessResult:
    status: ReadinessStatus
    target_trading_date: date
    data_ready_at: datetime | None = None
    latest_available_date: date | None = None

    @property
    def ready(self) -> bool:
        return self.status == ReadinessStatus.READY


class TradingCalendar(Protocol):
    def session(self, target_trading_date: date) -> TradingSession | None: ...


class NSETradingCalendar:
    """Offline NSE session calendar backed by maintained packaged rules."""

    def __init__(
        self,
        calendar_name: str | None = None,
        close_grace_minutes: int | None = None,
    ) -> None:
        self.calendar_name = calendar_name or settings.market_calendar
        self.close_grace_minutes = (
            close_grace_minutes
            if close_grace_minutes is not None
            else settings.market_close_grace_minutes
        )
        self._calendar = market_calendars.get_calendar(self.calendar_name)

    def session(self, target_trading_date: date) -> TradingSession | None:
        schedule = self._calendar.schedule(
            start_date=target_trading_date,
            end_date=target_trading_date,
            tz="UTC",
        )
        if schedule.empty:
            return None
        row = schedule.iloc[0]
        opens_at = row["market_open"].to_pydatetime()
        closes_at = row["market_close"].to_pydatetime()
        return TradingSession(
            trading_date=target_trading_date,
            opens_at=opens_at,
            closes_at=closes_at,
            data_ready_at=closes_at + timedelta(minutes=self.close_grace_minutes),
        )


class MarketProviderReadinessChecker:
    """Confirm a real, finalized target-session bar is available before ingestion."""

    def __init__(
        self,
        calendar: TradingCalendar,
        client: MarketDataClient,
        *,
        readiness_symbol: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.calendar = calendar
        self.client = client
        self.readiness_symbol = readiness_symbol or settings.market_readiness_symbol
        self.timeout_seconds = timeout_seconds or settings.market_fetch_timeout_seconds

    async def check(
        self, target_trading_date: date, *, now: datetime | None = None
    ) -> ReadinessResult:
        session = self.calendar.session(target_trading_date)
        if session is None:
            return ReadinessResult(ReadinessStatus.NON_TRADING_DAY, target_trading_date)

        if (as_utc(now) if now is not None else utc_now()) < session.data_ready_at:
            return ReadinessResult(
                ReadinessStatus.TOO_EARLY,
                target_trading_date,
                data_ready_at=session.data_ready_at,
            )

        try:
            bars = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.fetch_daily_prices,
                    self.readiness_symbol,
                    start_date=target_trading_date,
                    end_date=target_trading_date + timedelta(days=1),
                ),
                timeout=self.timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - provider has heterogeneous errors
            logger.warning(
                "eod_readiness_provider_unavailable",
                extra={
                    "target_trading_date": target_trading_date.isoformat(),
                    "provider": type(self.client).__name__,
                    "error": type(exc).__name__,
                },
            )
            return ReadinessResult(
                ReadinessStatus.PROVIDER_UNAVAILABLE,
                target_trading_date,
                data_ready_at=session.data_ready_at,
            )

        available_dates = {bar.date for bar in bars}
        latest = max(available_dates, default=None)
        if target_trading_date not in available_dates:
            return ReadinessResult(
                ReadinessStatus.DATA_NOT_READY,
                target_trading_date,
                data_ready_at=session.data_ready_at,
                latest_available_date=latest,
            )
        return ReadinessResult(
            ReadinessStatus.READY,
            target_trading_date,
            data_ready_at=session.data_ready_at,
            latest_available_date=latest,
        )


def build_readiness_checker() -> MarketProviderReadinessChecker:
    return MarketProviderReadinessChecker(
        NSETradingCalendar(),
        build_default_client(),
    )


async def check_eod_readiness(
    target_trading_date: date,
) -> ReadinessResult:
    """Run the production EOD preflight without persisting pipeline state."""
    return await build_readiness_checker().check(target_trading_date)
