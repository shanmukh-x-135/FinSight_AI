"""One-shot news/sentiment maintenance entrypoint.

This intentionally runs only the existing deterministic news pipeline. It is
used when a completed durable EOD session must not be reopened but current RSS
articles still need to be fetched, retagged, and re-aggregated.
"""

from __future__ import annotations

import asyncio

from app.news.service import NewsService
from app.shared.database import SessionFactory, dispose_engine
from config.logging import configure_logging, get_logger

logger = get_logger(__name__)

EXIT_SUCCESS = 0
EXIT_REFRESH_FAILED = 1


async def execute_once() -> int:
    """Run one idempotent news refresh and return a process exit code."""
    try:
        async with SessionFactory() as db:
            result = await NewsService(db).ingest()
        logger.info(
            "news_refresh_completed",
            extra=result.model_dump(),
        )
        return EXIT_SUCCESS
    except Exception as exc:  # noqa: BLE001 - process boundary logs safe class only
        logger.error(
            "news_refresh_failed",
            extra={"error": type(exc).__name__},
        )
        return EXIT_REFRESH_FAILED
    finally:
        await dispose_engine()


def main() -> int:
    """Configure structured logging and execute the one-shot refresh."""
    configure_logging()
    return asyncio.run(execute_once())


if __name__ == "__main__":
    raise SystemExit(main())
