"""Historical-intelligence HTTP routes.

* ``history_router``       → ``/api/v1/history/similar`` (public read).
* ``history_admin_router`` → ``/api/v1/admin/jobs/history-rebuild/run`` (auth).
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.history.service import HistoryService
from app.shared.database import get_db
from app.shared.response import envelope

history_router = APIRouter(prefix="/history", tags=["history"])
history_admin_router = APIRouter(prefix="/admin", tags=["admin"])


@history_router.get(
    "/similar",
    summary="Top-K historically similar sessions with next-day statistics",
    description="Finds the trading sessions most similar to the query date "
    "(default: latest) and summarizes what happened the next day.",
)
async def similar_sessions(
    date: date | None = Query(default=None, description="Query session date (YYYY-MM-DD)"),
    k: int | None = Query(default=None, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await HistoryService(db).query_similar(query_date=date, k=k)
    return envelope(data=result)


@history_admin_router.post(
    "/jobs/history-rebuild/run",
    summary="Rebuild the historical similarity index (dev/ops)",
    description="Re-engineers feature vectors from market data, refits the "
    "normalizer, and rebuilds the FAISS index. Auth-protected.",
)
async def rebuild_history_index(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await HistoryService(db).build_index()
    return envelope(data=result, message="Historical similarity index rebuilt.")
