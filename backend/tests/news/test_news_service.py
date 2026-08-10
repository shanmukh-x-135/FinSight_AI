"""Integration tests for the news ingestion → tag → score → aggregate pipeline."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.repository import MarketRepository
from app.news.models import NewsArticle, SentimentDaily
from app.news.service import NewsService
from app.shared.ml.sentiment import LexiconScorer
from tests.news.conftest import FakeNewsClient, make_item

BAD = "Reliance shares plunge as company reports massive loss and cuts dividend"
GOOD = "TCS profit surges, beats estimates and rallies to record high"
NEUTRAL = "Markets closed for a public holiday on Monday"


def _service(db: AsyncSession, items) -> NewsService:
    return NewsService(db, scorer=LexiconScorer(), client=FakeNewsClient(items))


@pytest.mark.asyncio
async def test_ingest_scores_tags_and_aggregates(
    db_session: AsyncSession, seed_stocks: None
) -> None:
    items = [
        make_item("http://x/1", BAD),
        make_item("http://x/2", GOOD),
        make_item("http://x/3", NEUTRAL),
    ]
    result = await _service(db_session, items).ingest()

    assert result.fetched == 3
    assert result.new_articles == 3
    assert result.tagged_articles == 2  # BAD→Reliance, GOOD→TCS, NEUTRAL→none

    # DoD: a clearly bad-news day shows NEGATIVE aggregate sentiment for that stock.
    reliance = await MarketRepository(db_session).get_stock_by_symbol("RELIANCE.NS")
    row = await db_session.scalar(
        select(SentimentDaily).where(
            SentimentDaily.stock_id == reliance.id, SentimentDaily.date == date(2024, 3, 1)
        )
    )
    assert row is not None
    assert row.avg_sentiment < 0
    assert row.negative_count == 1

    tcs = await MarketRepository(db_session).get_stock_by_symbol("TCS.NS")
    tcs_row = await db_session.scalar(
        select(SentimentDaily).where(SentimentDaily.stock_id == tcs.id)
    )
    assert tcs_row.avg_sentiment > 0


@pytest.mark.asyncio
async def test_reingest_deduplicates(
    db_session: AsyncSession, seed_stocks: None
) -> None:
    items = [make_item("http://x/1", BAD), make_item("http://x/2", GOOD)]
    await _service(db_session, items).ingest()
    second = await _service(db_session, items).ingest()  # same URLs

    assert second.new_articles == 0
    count = await db_session.scalar(select(func.count()).select_from(NewsArticle))
    assert count == 2  # no duplicates


@pytest.mark.asyncio
async def test_ingest_dedupes_same_title_across_feeds(
    db_session: AsyncSession, seed_stocks: None
) -> None:
    # Same story from two feeds (different URL, identical title) → stored once.
    items = [
        make_item("http://feedA/1", "Reliance surges on strong profit"),
        make_item("http://feedB/9", "Reliance surges on strong profit"),
    ]
    result = await _service(db_session, items).ingest()
    assert result.new_articles == 1


@pytest.mark.asyncio
async def test_reingest_dedupes_same_story_at_a_different_url(
    db_session: AsyncSession, seed_stocks: None
) -> None:
    title = "Reliance surges on strong profit"
    await _service(db_session, [make_item("http://feedA/1", title)]).ingest()
    second = await _service(db_session, [make_item("http://feedB/9", title)]).ingest()

    assert second.new_articles == 0
    count = await db_session.scalar(select(func.count()).select_from(NewsArticle))
    assert count == 1


@pytest.mark.asyncio
async def test_same_headline_on_a_later_day_is_a_distinct_story(
    db_session: AsyncSession, seed_stocks: None
) -> None:
    title = "Reliance announces quarterly results"
    first_day = datetime(2024, 3, 1, 10, tzinfo=timezone.utc)
    second_day = datetime(2024, 3, 2, 10, tzinfo=timezone.utc)
    result = await _service(
        db_session,
        [
            make_item("http://feed/1", title, published_at=first_day),
            make_item("http://feed/2", title, published_at=second_day),
        ],
    ).ingest()

    assert result.new_articles == 2


@pytest.mark.asyncio
async def test_aggregate_averages_multiple_articles(
    db_session: AsyncSession, seed_stocks: None
) -> None:
    # Two Reliance articles on the same day: one positive, one negative → averaged.
    items = [
        make_item("http://x/1", "Reliance surges on strong profit and record growth"),
        make_item("http://x/2", "Reliance falls on weak results and rising losses"),
    ]
    await _service(db_session, items).ingest()

    reliance = await MarketRepository(db_session).get_stock_by_symbol("RELIANCE.NS")
    row = await db_session.scalar(
        select(SentimentDaily).where(SentimentDaily.stock_id == reliance.id)
    )
    assert row.article_count == 2
    assert row.positive_count == 1
    assert row.negative_count == 1
