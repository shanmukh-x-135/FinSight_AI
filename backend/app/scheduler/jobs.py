"""Background jobs.

Jobs run outside the request cycle, so they open their own DB session from the
session factory (not the request-scoped ``get_db`` dependency).
"""

from __future__ import annotations

from app.market.service import MarketIngestionService
from app.shared.database import SessionFactory
from config.logging import get_logger

logger = get_logger(__name__)


async def market_ingestion_job() -> None:
    """Post-market-close job: ingest the default universe and store indicators."""
    logger.info("scheduled_ingestion_start")
    async with SessionFactory() as db:
        result = await MarketIngestionService(db).ingest()
    logger.info(
        "scheduled_ingestion_done",
        extra={"ok": len(result.succeeded), "failed": len(result.failed)},
    )
