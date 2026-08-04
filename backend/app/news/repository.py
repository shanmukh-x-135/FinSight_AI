"""Data-access for the news domain."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.news.models import NewsArticle, NewsArticleStock, SentimentDaily


class NewsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ----- Articles -------------------------------------------------------
    async def existing_urls(self, urls: list[str]) -> set[str]:
        if not urls:
            return set()
        result = await self.db.execute(
            select(NewsArticle.url).where(NewsArticle.url.in_(urls))
        )
        return set(result.scalars().all())

    async def add_article(self, article: NewsArticle) -> NewsArticle:
        self.db.add(article)
        await self.db.flush()
        return article

    async def add_tag(self, article_id: int, stock_id: int) -> None:
        self.db.add(NewsArticleStock(article_id=article_id, stock_id=stock_id))

    async def list_recent_articles(self, limit: int = 50) -> list[NewsArticle]:
        result = await self.db.execute(
            select(NewsArticle)
            .options(selectinload(NewsArticle.tags))
            .order_by(NewsArticle.fetched_at.desc(), NewsArticle.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def all_tagged_rows(self) -> list[tuple]:
        """(stock_id, published_at, fetched_at, sentiment_score, sentiment_label)."""
        result = await self.db.execute(
            select(
                NewsArticleStock.stock_id,
                NewsArticle.published_at,
                NewsArticle.fetched_at,
                NewsArticle.sentiment_score,
                NewsArticle.sentiment_label,
            ).join(NewsArticle, NewsArticle.id == NewsArticleStock.article_id)
        )
        return list(result.all())

    # ----- Daily sentiment aggregate --------------------------------------
    async def upsert_sentiment_daily(
        self, stock_id: int, day: date, *, avg: float, pos: int, neg: int, neu: int
    ) -> None:
        result = await self.db.execute(
            select(SentimentDaily).where(
                SentimentDaily.stock_id == stock_id, SentimentDaily.date == day
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = SentimentDaily(stock_id=stock_id, date=day)
            self.db.add(row)
        row.avg_sentiment = avg
        row.article_count = pos + neg + neu
        row.positive_count = pos
        row.negative_count = neg
        row.neutral_count = neu
        await self.db.flush()

    async def get_sentiment_series(self, stock_id: int) -> list[SentimentDaily]:
        result = await self.db.execute(
            select(SentimentDaily)
            .where(SentimentDaily.stock_id == stock_id)
            .order_by(SentimentDaily.date.asc())
        )
        return list(result.scalars().all())
