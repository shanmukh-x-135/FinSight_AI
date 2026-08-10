"""Data-access for the news domain."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.market.models import Stock
from app.news.models import NewsArticle, NewsArticleStock, SentimentDaily
from app.shared.upsert import conflict_insert


class NewsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ----- Articles -------------------------------------------------------
    async def existing_article_keys(
        self, urls: list[str], fingerprints: list[str]
    ) -> tuple[set[str], set[str]]:
        if not urls and not fingerprints:
            return set(), set()
        result = await self.db.execute(
            select(NewsArticle.url, NewsArticle.fingerprint).where(
                NewsArticle.url.in_(urls) | NewsArticle.fingerprint.in_(fingerprints)
            )
        )
        rows = result.all()
        return {row.url for row in rows}, {row.fingerprint for row in rows}

    async def add_article(self, article: NewsArticle) -> int | None:
        """Insert once by either URL or fingerprint; return the new id if won."""
        values = {
            column.name: getattr(article, column.name)
            for column in NewsArticle.__table__.columns
            if column.name not in {"id", "fetched_at"}
        }
        stmt = conflict_insert(self.db, NewsArticle).values(**values)
        result = await self.db.execute(
            stmt.on_conflict_do_nothing().returning(NewsArticle.id)
        )
        return result.scalar_one_or_none()

    async def add_tag(self, article_id: int, stock_id: int) -> None:
        stmt = conflict_insert(self.db, NewsArticleStock).values(
            article_id=article_id, stock_id=stock_id
        )
        await self.db.execute(stmt.on_conflict_do_nothing())

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
        stmt = conflict_insert(self.db, SentimentDaily).values(
            stock_id=stock_id,
            date=day,
            avg_sentiment=avg,
            article_count=pos + neg + neu,
            positive_count=pos,
            negative_count=neg,
            neutral_count=neu,
        )
        result = await self.db.execute(
            stmt.on_conflict_do_update(
                index_elements=[SentimentDaily.stock_id, SentimentDaily.date],
                set_={
                    "avg_sentiment": stmt.excluded.avg_sentiment,
                    "article_count": stmt.excluded.article_count,
                    "positive_count": stmt.excluded.positive_count,
                    "negative_count": stmt.excluded.negative_count,
                    "neutral_count": stmt.excluded.neutral_count,
                    "updated_at": func.now(),
                },
            )
            .returning(SentimentDaily)
            .execution_options(populate_existing=True)
        )
        result.scalars().all()

    async def get_latest_sentiment_map(self) -> dict[int, float]:
        """Most-recent avg_sentiment per stock (for context building)."""
        result = await self.db.execute(
            select(SentimentDaily.stock_id, SentimentDaily.date, SentimentDaily.avg_sentiment)
            .order_by(SentimentDaily.stock_id, SentimentDaily.date.asc())
        )
        latest: dict[int, float] = {}
        for stock_id, _day, value in result.all():
            latest[stock_id] = value  # ascending → last write wins = most recent
        return latest

    async def get_sentiment_series(self, stock_id: int) -> list[SentimentDaily]:
        result = await self.db.execute(
            select(SentimentDaily)
            .where(SentimentDaily.stock_id == stock_id)
            .order_by(SentimentDaily.date.asc())
        )
        return list(result.scalars().all())

    async def get_sector_sentiment_series(self, sector: str) -> list[tuple]:
        """Daily article-weighted sector sentiment aggregated from stock rows."""
        count = func.sum(SentimentDaily.article_count)
        result = await self.db.execute(
            select(
                SentimentDaily.date,
                func.sum(
                    SentimentDaily.avg_sentiment * SentimentDaily.article_count
                )
                / count,
                count,
                func.sum(SentimentDaily.positive_count),
                func.sum(SentimentDaily.negative_count),
                func.sum(SentimentDaily.neutral_count),
            )
            .join(Stock, Stock.id == SentimentDaily.stock_id)
            .where(Stock.sector == sector)
            .group_by(SentimentDaily.date)
            .order_by(SentimentDaily.date.asc())
        )
        return list(result.all())
