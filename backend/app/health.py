"""Health-check endpoints.

Two liveness/readiness probes:

* ``GET /health``     — process is up (no dependencies touched).
* ``GET /health/db``  — the database is reachable and answering queries.

Kept deliberately outside the versioned ``/api/v1`` namespace: these are
infrastructure probes for Docker/Render/Vercel, not part of the product API.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from config.constants import HEALTH_DEGRADED, HEALTH_OK
from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    """Return 200 if the API process is running."""
    return {"status": HEALTH_OK, "service": settings.app_name, "env": settings.app_env}


@router.get("/health/db", summary="Database readiness probe")
async def health_db(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Return 200 if a trivial query against the database succeeds, else 503."""
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar_one()
    except Exception:  # noqa: BLE001 — we want to catch *any* connectivity failure
        logger.error("health_db_failed")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": HEALTH_DEGRADED, "database": "unreachable"},
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": HEALTH_OK, "database": "reachable"},
    )
