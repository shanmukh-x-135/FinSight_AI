"""APScheduler lifecycle.

An AsyncIOScheduler is started/stopped in each app process (see ``app/main.py``).
It registers the post-market-close market-ingestion job; the job itself uses a
PostgreSQL advisory lock so only one process executes the pipeline. Jobs are
additive here; later phases hook into the same scheduler, matching the design
doc's event-driven pipeline.

Guarded by ``settings.scheduler_enabled`` so it can be turned off (e.g. in
environments that shouldn't run background work).
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.scheduler.jobs import market_ingestion_job
from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None

MARKET_INGESTION_JOB_ID = "market_ingestion"


def start_scheduler() -> None:
    """Create, configure, and start the scheduler (idempotent)."""
    global _scheduler
    if not settings.scheduler_enabled:
        logger.info("scheduler_disabled")
        return
    if _scheduler is not None and _scheduler.running:
        return

    _scheduler = AsyncIOScheduler(timezone=settings.market_timezone)
    _scheduler.add_job(
        market_ingestion_job,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=settings.market_ingestion_hour,
            minute=settings.market_ingestion_minute,
            timezone=settings.market_timezone,
        ),
        id=MARKET_INGESTION_JOB_ID,
        replace_existing=True,
        misfire_grace_time=3600,  # tolerate a late start (e.g. brief downtime)
        coalesce=True,
    )
    _scheduler.start()
    logger.info(
        "scheduler_started",
        extra={
            "timezone": settings.market_timezone,
            "ingestion_time": f"{settings.market_ingestion_hour:02d}:"
            f"{settings.market_ingestion_minute:02d}",
        },
    )


def shutdown_scheduler() -> None:
    """Stop the scheduler on app shutdown."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")
    _scheduler = None
