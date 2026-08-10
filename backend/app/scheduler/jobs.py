"""Domain-step adapters and the one-shot EOD pipeline invocation."""

from __future__ import annotations

from datetime import date

from app.history.service import HistoryService
from app.market.service import MarketIngestionService
from app.news.service import NewsService
from app.scheduler.constants import EOD_PIPELINE_NAME, PipelineStepName
from app.scheduler.control_plane import (
    EODControlPlane,
    PipelineExecutionResult,
    StepExecutionError,
)
from app.shared.database import SessionFactory
from config.logging import get_logger

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


async def run_eod_pipeline(target_trading_date: date) -> PipelineExecutionResult:
    """Invoke the durable EOD pipeline for an explicit target trading date."""
    result = await build_eod_control_plane().execute(
        EOD_PIPELINE_NAME, target_trading_date
    )
    logger.info(
        "eod_pipeline_finished",
        extra={
            "pipeline_name": EOD_PIPELINE_NAME,
            "target_trading_date": target_trading_date.isoformat(),
            "run_id": result.run_id,
            "correlation_id": result.correlation_id,
            "status": result.status.value if result.status else None,
            "lock_acquired": result.acquired,
        },
    )
    return result
