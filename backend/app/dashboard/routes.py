"""Dashboard HTTP route (auth-protected).

One combined read that backs the Phase 7 home screen — batched to avoid the
per-card round trips the roadmap warns against.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.dashboard.schemas import DashboardSummaryOut
from app.dashboard.service import DashboardService
from app.shared.database import get_db
from app.shared.response import envelope

dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@dashboard_router.get(
    "/summary",
    summary=(
        "Combined dashboard summary (market, portfolio, watchlist, AI, opportunities)"
    ),
)
async def dashboard_summary(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    data = await DashboardService(db).build_summary(user.id)
    return envelope(data=DashboardSummaryOut(**data))
