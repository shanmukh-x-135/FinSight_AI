"""News & sentiment HTTP routes.

* ``news_router``       → ``/api/v1/news`` (public reads).
* ``news_admin_router`` → ``/api/v1/admin/jobs/news-ingestion/run`` (auth).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_admin_user
from app.auth.models import User
from app.news.dependencies import get_news_client, get_news_scorer
from app.news.service import NewsService
from app.shared.clients.news_client import NewsClient
from app.shared.database import get_db
from app.shared.ml.sentiment import SentimentScorer
from app.shared.response import envelope

news_router = APIRouter(prefix="/news", tags=["news"])
news_admin_router = APIRouter(prefix="/admin", tags=["admin"])


@news_router.get("", summary="Recent financial news with sentiment")
async def recent_news(
    limit: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_db)
) -> dict:
    return envelope(data=await NewsService(db).list_recent(limit))


@news_router.get("/sentiment", summary="Latest sentiment for the active stock universe")
async def latest_sentiment(db: AsyncSession = Depends(get_db)) -> dict:
    return envelope(data=await NewsService(db).list_latest_sentiment())


@news_router.get("/sentiment/{symbol}", summary="Daily sentiment series for a stock")
async def stock_sentiment(symbol: str, db: AsyncSession = Depends(get_db)) -> dict:
    return envelope(data=await NewsService(db).get_stock_sentiment(symbol))


@news_router.get(
    "/sentiment/sector/{sector}", summary="Daily article-weighted sentiment for a sector"
)
async def sector_sentiment(sector: str, db: AsyncSession = Depends(get_db)) -> dict:
    return envelope(data=await NewsService(db).get_sector_sentiment(sector))


@news_admin_router.post(
    "/jobs/news-ingestion/run",
    summary="Manually trigger news ingestion + sentiment scoring (dev/ops)",
    description="Fetches feeds, scores sentiment, tags companies, and aggregates "
    "daily sentiment. Auth-protected.",
)
async def run_news_ingestion(
    _user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    client: NewsClient = Depends(get_news_client),
    scorer: SentimentScorer = Depends(get_news_scorer),
) -> dict:
    result = await NewsService(db, scorer=scorer, client=client).ingest()
    return envelope(data=result, message="News ingestion complete.")


@news_admin_router.get(
    "/jobs/news-ingestion/status",
    summary="Inspect aggregate news-ingestion and sentiment health",
    description="Returns counts and timestamps only; article content is never included.",
)
async def news_ingestion_status(
    _user: User = Depends(get_admin_user),
    recent_window_days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await NewsService(db).get_diagnostics(recent_window_days)
    return envelope(data=result, message="News ingestion status loaded.")
