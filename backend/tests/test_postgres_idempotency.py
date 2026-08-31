"""PostgreSQL integration coverage for concurrent, duplicate domain writes."""

from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.intelligence.models import Report
from app.market.models import DailyPrice, Stock
from app.market.repository import MarketRepository
from app.news.models import NewsArticle
from app.news.repository import NewsRepository
from app.reports.repository import ReportRepository
from app.shared.clients.market_data import PriceBar

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL, reason="TEST_POSTGRES_URL is required for PostgreSQL integration"
)


@pytest.mark.asyncio
async def test_postgres_concurrent_writers_preserve_one_logical_row() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_size=6)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid4().hex[:12]
    symbol = f"IDEM-{suffix}.NS"
    url = f"https://example.invalid/{suffix}"
    fingerprint = uuid4().hex + uuid4().hex
    report_hash = uuid4().hex + uuid4().hex
    bar = PriceBar(date=date(2099, 1, 5), open=100, high=102, low=99, close=101, volume=7)

    async def write_market(close: float) -> None:
        async with factory() as db:
            stock = await MarketRepository(db).upsert_stock(
                symbol,
                name="Idempotency Test",
                sector=None,
                industry=None,
                exchange="NSE",
            )
            await MarketRepository(db).upsert_daily_prices(
                stock.id, [PriceBar(**{**bar.__dict__, "close": close})]
            )
            await db.commit()

    async def write_news(source: str) -> None:
        async with factory() as db:
            article = NewsArticle(
                source=source,
                url=url,
                fingerprint=fingerprint,
                title="Concurrent story",
                summary="",
                published_at=datetime(2099, 1, 5, tzinfo=timezone.utc),
                sentiment_label="neutral",
                sentiment_score=0,
                sentiment_positive=0,
                sentiment_negative=0,
                sentiment_neutral=1,
            )
            await NewsRepository(db).add_article(article)
            await db.commit()

    async def write_report(marker: str) -> int:
        async with factory() as db:
            report = await ReportRepository(db).create_report(
                None,
                "daily",
                {"marker": marker},
                idempotency_key_hash=report_hash,
            )
            await db.commit()
            return report.id

    try:
        await asyncio.gather(write_market(101), write_market(102))
        await asyncio.gather(write_news("feed-a"), write_news("feed-b"))
        report_ids = await asyncio.gather(write_report("a"), write_report("b"))

        async with factory() as db:
            stock_id = await db.scalar(select(Stock.id).where(Stock.symbol == symbol))
            assert stock_id is not None
            assert await db.scalar(
                select(func.count(DailyPrice.id)).where(DailyPrice.stock_id == stock_id)
            ) == 1
            assert await db.scalar(
                select(func.count(NewsArticle.id)).where(
                    NewsArticle.fingerprint == fingerprint
                )
            ) == 1
            persisted_article = await db.scalar(
                select(NewsArticle).where(NewsArticle.fingerprint == fingerprint)
            )
            assert persisted_article is not None
            assert persisted_article.sentiment_confidence == pytest.approx(0.6)
            assert persisted_article.event_category == "Other"
            assert persisted_article.event_confidence == pytest.approx(0.35)
            assert persisted_article.evidence_excerpt == "Concurrent story"
            assert await db.scalar(
                select(func.count(Report.id)).where(
                    Report.idempotency_key_hash == report_hash
                )
            ) == 1
            assert report_ids[0] == report_ids[1]
    finally:
        async with factory.begin() as db:
            await db.execute(delete(Report).where(Report.idempotency_key_hash == report_hash))
            await db.execute(delete(NewsArticle).where(NewsArticle.fingerprint == fingerprint))
            await db.execute(delete(Stock).where(Stock.symbol == symbol))
        await engine.dispose()
