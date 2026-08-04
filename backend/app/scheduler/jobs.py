"""Background jobs.

Jobs run outside the request cycle, so they open their own DB session from the
session factory (not the request-scoped ``get_db`` dependency).
"""

from __future__ import annotations

from app.history.service import HistoryService
from app.market.service import MarketIngestionService
from app.news.service import NewsService
from app.shared.database import SessionFactory
from config.logging import get_logger

logger = get_logger(__name__)


async def market_ingestion_job() -> None:
    """Post-market-close pipeline (design doc §4.5): ingest market data → ingest
    news + score sentiment → rebuild the historical similarity index.

    Each downstream step is best-effort — a later step's failure must not undo an
    earlier step's success.
    """
    logger.info("scheduled_ingestion_start")
    async with SessionFactory() as db:
        result = await MarketIngestionService(db).ingest()
    logger.info(
        "scheduled_ingestion_done",
        extra={"ok": len(result.succeeded), "failed": len(result.failed)},
    )

    try:
        async with SessionFactory() as db:
            news = await NewsService(db).ingest()
        logger.info(
            "scheduled_news_done",
            extra={"new": news.new_articles, "tagged": news.tagged_articles},
        )
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.error(
            "scheduled_news_failed",
            extra={"error": type(exc).__name__, "detail": str(exc)},
        )

    try:
        async with SessionFactory() as db:
            rebuild = await HistoryService(db).build_index()
        logger.info(
            "scheduled_history_rebuild_done",
            extra={"sessions": rebuild.sessions_indexed},
        )
    except Exception as exc:  # noqa: BLE001 — best-effort, never crash the job
        logger.error(
            "scheduled_history_rebuild_failed",
            extra={"error": type(exc).__name__, "detail": str(exc)},
        )
