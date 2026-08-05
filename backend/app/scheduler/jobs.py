"""Thin scheduler caller and adapters for the durable EOD control plane."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.history.service import HistoryService
from app.market.service import MarketIngestionService
from app.news.service import NewsService
from app.scheduler.constants import EOD_PIPELINE_NAME, PipelineStepName
from app.scheduler.control_plane import EODControlPlane, StepExecutionError
from app.shared.database import SessionFactory
from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)


async def _run_market_step(_target_trading_date: date) -> dict[str, int]:
    async with SessionFactory() as db:
        result = await MarketIngestionService(db).ingest()
    counters = {
        "requested": result.requested,
        "succeeded": len(result.succeeded),
        "failed": len(result.failed),
    }
    if result.failed:
        raise StepExecutionError(
            f"Market ingestion failed for {len(result.failed)} symbol(s)", counters
        )
    return counters


async def _run_news_step(_target_trading_date: date) -> dict[str, int]:
    async with SessionFactory() as db:
        result = await NewsService(db).ingest()
    return {
        "fetched": result.fetched,
        "new_articles": result.new_articles,
        "tagged_articles": result.tagged_articles,
        "sentiment_days_updated": result.sentiment_days_updated,
    }


async def _run_history_step(_target_trading_date: date) -> dict[str, int]:
    async with SessionFactory() as db:
        result = await HistoryService(db).build_index()
    return {"sessions_indexed": result.sessions_indexed, "dimension": result.dim}


def build_eod_control_plane() -> EODControlPlane:
    """Build the production control plane around the existing domain services."""
    return EODControlPlane(
        SessionFactory,
        {
            PipelineStepName.MARKET: _run_market_step,
            PipelineStepName.NEWS: _run_news_step,
            PipelineStepName.HISTORY: _run_history_step,
        },
    )


def current_market_date() -> date:
    """Return today's market-local date; holiday validation arrives in P10.3."""
    return datetime.now(ZoneInfo(settings.market_timezone)).date()


async def market_ingestion_job(target_trading_date: date | None = None) -> None:
    """Invoke the resumable EOD pipeline for an explicit target trading date.

    APScheduler may omit the argument temporarily; in that case this thin caller
    supplies the current market-local date. Trading-calendar validation is P10.3.
    """
    target = target_trading_date or current_market_date()
    result = await build_eod_control_plane().execute(EOD_PIPELINE_NAME, target)
    logger.info(
        "scheduled_eod_pipeline_finished",
        extra={
            "pipeline_name": EOD_PIPELINE_NAME,
            "target_trading_date": target.isoformat(),
            "run_id": result.run_id,
            "correlation_id": result.correlation_id,
            "status": result.status.value if result.status else None,
            "lock_acquired": result.acquired,
        },
    )
