"""One-shot process entrypoint for an external EOD scheduler.

Usage::

    python -m app.scheduler.runner --target-trading-date 2026-08-05

When the date is omitted, the runner resolves the latest NSE session whose bar
the provider confirms is ready. This remains correct when a delayed invocation
crosses midnight, a weekend, or a holiday.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.intelligence.llm_client import close_llm_client
from app.scheduler.constants import PipelineRunStatus
from app.scheduler.jobs import get_eod_run_status, run_eod_pipeline
from app.scheduler.readiness import (
    NSETradingCalendar,
    ReadinessResult,
    ReadinessStatus,
    TradingCalendar,
    check_eod_readiness,
)
from app.shared.database import dispose_engine
from app.shared.time import utc_now
from config.logging import configure_logging, get_logger
from config.settings import settings

logger = get_logger(__name__)

EXIT_SUCCESS = 0
EXIT_PIPELINE_INCOMPLETE = 1


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "must be an ISO date in YYYY-MM-DD format"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the FinSight EOD pipeline exactly once."
    )
    parser.add_argument(
        "--target-trading-date",
        type=_iso_date,
        help=(
            "Target trading date in YYYY-MM-DD format. Defaults to the latest "
            "provider-ready NSE trading session."
        ),
    )
    return parser


def current_market_date(now: datetime | None = None) -> date:
    """Resolve the calendar date in the configured market timezone."""
    instant = now or utc_now()
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(ZoneInfo(settings.market_timezone)).date()


async def resolve_latest_provider_ready_trading_date(
    *,
    now: datetime | None = None,
    calendar: TradingCalendar | None = None,
    readiness_check: Callable[[date], Awaitable[ReadinessResult]] | None = None,
) -> date | None:
    """Walk backward to the newest NSE session the provider confirms as ready."""
    market_date = current_market_date(now)
    sessions = calendar or NSETradingCalendar()
    check = readiness_check or check_eod_readiness
    for offset in range(10):
        candidate = market_date - timedelta(days=offset)
        if sessions.session(candidate) is None:
            continue
        readiness = await check(candidate)
        if readiness.ready:
            return candidate
    return None


async def execute_once(target_trading_date: date) -> int:
    """Execute one external-runner attempt and map its result to a process code."""
    try:
        existing_status = await get_eod_run_status(target_trading_date)
        if existing_status == PipelineRunStatus.COMPLETED:
            logger.info(
                "eod_runner_already_completed",
                extra={"target_trading_date": target_trading_date.isoformat()},
            )
            return EXIT_SUCCESS

        readiness = await check_eod_readiness(target_trading_date)
        if readiness.status == ReadinessStatus.NON_TRADING_DAY:
            logger.info(
                "eod_runner_non_trading_day_skipped",
                extra={"target_trading_date": target_trading_date.isoformat()},
            )
            return EXIT_SUCCESS
        if not readiness.ready:
            logger.warning(
                "eod_runner_provider_not_ready",
                extra={
                    "target_trading_date": target_trading_date.isoformat(),
                    "readiness_status": readiness.status.value,
                    "data_ready_at": (
                        readiness.data_ready_at.isoformat()
                        if readiness.data_ready_at
                        else None
                    ),
                    "latest_available_date": (
                        readiness.latest_available_date.isoformat()
                        if readiness.latest_available_date
                        else None
                    ),
                },
            )
            return EXIT_PIPELINE_INCOMPLETE

        result = await run_eod_pipeline(target_trading_date)
        if not result.acquired:
            logger.info(
                "eod_runner_duplicate_skipped",
                extra={"target_trading_date": target_trading_date.isoformat()},
            )
            return EXIT_SUCCESS
        if result.status == PipelineRunStatus.COMPLETED:
            logger.info(
                "eod_runner_completed",
                extra={
                    "target_trading_date": target_trading_date.isoformat(),
                    "run_id": result.run_id,
                    "correlation_id": result.correlation_id,
                },
            )
            return EXIT_SUCCESS
        logger.error(
            "eod_runner_incomplete",
            extra={
                "target_trading_date": target_trading_date.isoformat(),
                "run_id": result.run_id,
                "correlation_id": result.correlation_id,
                "status": result.status.value if result.status else None,
            },
        )
        return EXIT_PIPELINE_INCOMPLETE
    except Exception as exc:  # noqa: BLE001 - process boundary reports safe class only
        logger.error(
            "eod_runner_failed",
            extra={
                "target_trading_date": target_trading_date.isoformat(),
                "error": type(exc).__name__,
            },
        )
        return EXIT_PIPELINE_INCOMPLETE
    finally:
        try:
            await close_llm_client()
        finally:
            await dispose_engine()


async def execute_default_once() -> int:
    """Resolve the latest provider-ready session, then execute it once."""
    target = await resolve_latest_provider_ready_trading_date()
    if target is None:
        logger.warning("eod_runner_no_provider_ready_session")
        return EXIT_PIPELINE_INCOMPLETE
    return await execute_once(target)


def main(argv: Sequence[str] | None = None) -> int:
    """Parse one-shot runner arguments and return a shell-compatible exit code."""
    configure_logging()
    args = build_parser().parse_args(argv)
    if args.target_trading_date is not None:
        return asyncio.run(execute_once(args.target_trading_date))
    return asyncio.run(execute_default_once())


if __name__ == "__main__":
    raise SystemExit(main())
