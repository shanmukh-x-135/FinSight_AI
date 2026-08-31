"""Data-access for the news domain."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.market.models import Stock
from app.news.classification import (
    classify_event,
    evidence_excerpt,
    sentiment_confidence,
)
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
        event = classify_event(article.title, article.summary)
        values = {
            column.name: getattr(article, column.name)
            for column in NewsArticle.__table__.columns
            if column.name not in {"id", "fetched_at"}
        }
        # Repository callers include maintenance and concurrency paths that may
        # construct legacy article objects without Phase-11A enrichment. Keep
        # the persistence boundary non-null and deterministic for every caller.
        values.update(
            sentiment_confidence=(
                article.sentiment_confidence
                if article.sentiment_confidence is not None
                else sentiment_confidence(
                    score=article.sentiment_score,
                    positive=article.sentiment_positive,
                    negative=article.sentiment_negative,
                    neutral=article.sentiment_neutral,
                )
            ),
            event_category=article.event_category or event.category,
            event_confidence=(
                article.event_confidence
                if article.event_confidence is not None
                else event.confidence
            ),
            driver=article.driver or event.driver,
            evidence_excerpt=(
                article.evidence_excerpt
                or evidence_excerpt(article.title, article.summary)
            ),
        )
        stmt = conflict_insert(self.db, NewsArticle).values(**values)
        result = await self.db.execute(
            stmt.on_conflict_do_nothing().returning(NewsArticle.id)
        )
        return result.scalar_one_or_none()

    async def add_tag(
        self,
        article_id: int,
        stock_id: int,
        *,
        matching_alias: str | None = None,
        entity_match_confidence: float = 0.0,
    ) -> None:
        stmt = conflict_insert(self.db, NewsArticleStock).values(
            article_id=article_id,
            stock_id=stock_id,
            matching_alias=matching_alias,
            entity_match_confidence=entity_match_confidence,
        )
        await self.db.execute(
            stmt.on_conflict_do_update(
                index_elements=[NewsArticleStock.article_id, NewsArticleStock.stock_id],
                set_={
                    "matching_alias": stmt.excluded.matching_alias,
                    "entity_match_confidence": stmt.excluded.entity_match_confidence,
                },
            )
        )

    async def list_articles_since(self, since: datetime) -> list[NewsArticle]:
        result = await self.db.execute(
            select(NewsArticle)
            .options(selectinload(NewsArticle.tags))
            .where(
                or_(
                    NewsArticle.published_at >= since,
                    NewsArticle.fetched_at >= since,
                )
            )
            .order_by(NewsArticle.id)
        )
        return list(result.scalars().all())

    async def reconcile_tags(
        self,
        article: NewsArticle,
        desired_matches: dict[int, tuple[str, float]],
    ) -> tuple[int, int]:
        """Make one article's associations exactly match deterministic tagging."""
        current = {tag.stock_id for tag in article.tags}
        desired_stock_ids = set(desired_matches)
        to_add = desired_stock_ids - current
        to_remove = current - desired_stock_ids
        if to_remove:
            await self.db.execute(
                delete(NewsArticleStock)
                .where(
                    NewsArticleStock.article_id == article.id,
                    NewsArticleStock.stock_id.in_(to_remove),
                )
                .execution_options(synchronize_session=False)
            )
        for stock_id in desired_stock_ids:
            alias, confidence = desired_matches[stock_id]
            await self.add_tag(
                article.id,
                stock_id,
                matching_alias=alias,
                entity_match_confidence=confidence,
            )
        return len(to_add), len(to_remove)

    async def list_recent_stock_articles(
        self, stock_id: int, *, recent_since: datetime, limit: int = 20
    ) -> list[tuple[NewsArticle, NewsArticleStock]]:
        result = await self.db.execute(
            select(NewsArticle, NewsArticleStock)
            .join(NewsArticleStock, NewsArticleStock.article_id == NewsArticle.id)
            .where(
                NewsArticleStock.stock_id == stock_id,
                func.coalesce(NewsArticle.published_at, NewsArticle.fetched_at)
                >= recent_since,
            )
            .order_by(
                func.coalesce(NewsArticle.published_at, NewsArticle.fetched_at).desc(),
                NewsArticle.id.desc(),
            )
            .limit(limit)
        )
        return list(result.all())

    async def recent_stock_evidence_rows(self, *, recent_since: datetime) -> list[tuple]:
        result = await self.db.execute(
            select(
                NewsArticleStock.stock_id,
                NewsArticle.sentiment_score,
                NewsArticle.sentiment_label,
                NewsArticle.sentiment_confidence,
                NewsArticleStock.entity_match_confidence,
            )
            .join(NewsArticle, NewsArticle.id == NewsArticleStock.article_id)
            .where(
                func.coalesce(NewsArticle.published_at, NewsArticle.fetched_at)
                >= recent_since
            )
        )
        return list(result.all())

    async def list_recent_articles(
        self, limit: int = 50, *, recent_since: datetime
    ) -> list[NewsArticle]:
        result = await self.db.execute(
            select(NewsArticle)
            .options(selectinload(NewsArticle.tags))
            .where(
                func.coalesce(NewsArticle.published_at, NewsArticle.fetched_at)
                >= recent_since
            )
            .order_by(
                func.coalesce(NewsArticle.published_at, NewsArticle.fetched_at).desc(),
                NewsArticle.id.desc(),
            )
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

    async def sentiment_row_keys(self) -> list[tuple[int, int, date]]:
        result = await self.db.execute(
            select(SentimentDaily.id, SentimentDaily.stock_id, SentimentDaily.date)
        )
        return list(result.all())

    async def delete_sentiment_rows(self, row_ids: list[int]) -> None:
        if not row_ids:
            return
        await self.db.execute(
            delete(SentimentDaily)
            .where(SentimentDaily.id.in_(row_ids))
            .execution_options(synchronize_session=False)
        )

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

    async def get_latest_sentiment_map(
        self, *, recent_since: date | None = None
    ) -> dict[int, float]:
        """Most-recent average per stock, optionally bounded to recent sessions."""
        statement = select(
            SentimentDaily.stock_id, SentimentDaily.date, SentimentDaily.avg_sentiment
        )
        if recent_since is not None:
            statement = statement.where(SentimentDaily.date >= recent_since)
        result = await self.db.execute(
            statement.order_by(SentimentDaily.stock_id, SentimentDaily.date.asc())
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
                func.sum(SentimentDaily.avg_sentiment * SentimentDaily.article_count)
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

    async def diagnostics(
        self, *, recent_since: datetime
    ) -> dict[str, int | datetime | None]:
        """Return aggregate-only operational facts; never load article bodies."""
        article_row = (
            await self.db.execute(
                select(
                    func.count(NewsArticle.id),
                    func.sum(
                        case(
                            (
                                func.coalesce(
                                    NewsArticle.published_at, NewsArticle.fetched_at
                                )
                                >= recent_since,
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    func.sum(
                        case((NewsArticle.sentiment_label == "positive", 1), else_=0)
                    ),
                    func.sum(
                        case((NewsArticle.sentiment_label == "neutral", 1), else_=0)
                    ),
                    func.sum(
                        case((NewsArticle.sentiment_label == "negative", 1), else_=0)
                    ),
                    func.max(NewsArticle.fetched_at),
                )
            )
        ).one()
        linked_articles = await self.db.scalar(
            select(func.count(func.distinct(NewsArticleStock.article_id)))
        )
        associations = await self.db.scalar(select(func.count(NewsArticleStock.id)))
        active_linked = await self.db.scalar(
            select(func.count(func.distinct(NewsArticleStock.stock_id)))
            .join(Stock, Stock.id == NewsArticleStock.stock_id)
            .where(Stock.is_active.is_(True))
        )
        sentiment_rows = await self.db.scalar(select(func.count(SentimentDaily.id)))
        active_recent_sentiment = await self.db.scalar(
            select(func.count(func.distinct(SentimentDaily.stock_id)))
            .join(Stock, Stock.id == SentimentDaily.stock_id)
            .where(
                Stock.is_active.is_(True),
                SentimentDaily.date >= recent_since.date(),
            )
        )
        latest_sentiment_at = await self.db.scalar(
            select(func.max(SentimentDaily.updated_at))
        )
        return {
            "total_articles": article_row[0] or 0,
            "recent_articles": article_row[1] or 0,
            "positive_articles": article_row[2] or 0,
            "neutral_articles": article_row[3] or 0,
            "negative_articles": article_row[4] or 0,
            "latest_news_ingestion_at": article_row[5],
            "linked_articles": linked_articles or 0,
            "article_stock_associations": associations or 0,
            "distinct_active_stocks_with_links": active_linked or 0,
            "sentiment_rows": sentiment_rows or 0,
            "active_stocks_with_recent_sentiment": active_recent_sentiment or 0,
            "latest_sentiment_at": latest_sentiment_at,
        }
