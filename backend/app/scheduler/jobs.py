"""Background jobs.

Jobs run outside the request cycle, so they open their own DB session from the
session factory (not the request-scoped ``get_db`` dependency).
"""

from __future__ import annotations

from app.history.service import HistoryService
from app.market.service import MarketIngestionService
from app.shared.database import SessionFactory
from config.logging import get_logger

logger = get_logger(__name__)


async def market_ingestion_job() -> None:
    """Post-market-close pipeline: ingest market data, then rebuild the
    historical similarity index so it never goes stale (design doc §4.5).

    The index rebuild is best-effort — a rebuild failure (e.g. not enough
    history yet) must not undo a successful ingestion.
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
