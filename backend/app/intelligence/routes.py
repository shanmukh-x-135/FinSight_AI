"""Intelligence HTTP routes (auth-protected).

Report generation/listing/detail and export live in the reports module
(``app/reports/``) as of Phase 8; this router now exposes only the current
recommendations feed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.intelligence.schemas import RecommendationsOut
from app.intelligence.service import IntelligenceService
from app.shared.database import get_db
from app.shared.response import envelope

intelligence_router = APIRouter(tags=["intelligence"])


@intelligence_router.get(
    "/recommendations",
    summary="Current watchlist recommendations + risk alerts (evidence-backed)",
)
async def recommendations(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    data = await IntelligenceService(db).get_recommendations(user.id)
    return envelope(data=RecommendationsOut(**data))
