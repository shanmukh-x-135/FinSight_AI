"""Integration tests for the news ingestion → tag → score → aggregate pipeline."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.models import DailyPrice, Stock
from app.market.repository import MarketRepository
from app.news.models import NewsArticle, NewsArticleStock, SentimentDaily
from app.news.repository import NewsRepository
from app.news.service import NewsService
from app.shared.ml.sentiment import LexiconScorer
from tests.news.conftest import FakeNewsClient, make_item

BAD = "Reliance Industries shares plunge after massive loss and dividend cut"
GOOD = "TCS profit surges, beats estimates and rallies to record high"
NEUTRAL = "Markets closed for a public holiday on Monday"


def _service(db: AsyncSession, items) -> NewsService:
    return NewsService(db, scorer=LexiconScorer(), client=FakeNewsClient(items))


@pytest.mark.asyncio
async def test_repository_enriches_legacy_article_callers(
    db_session: AsyncSession,
) -> None:
    article = NewsArticle(
        source="Legacy writer",
        url="https://example.test/legacy-writer",
        fingerprint="f" * 64,
        title="Company quarterly profit rises",
        summary="Results beat estimates",
        published_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
        sentiment_label="positive",
        sentiment_score=0.5,
        sentiment_positive=0.75,
        sentiment_negative=0.25,
        sentiment_neutral=0,
    )
    article_id = await NewsRepository(db_session).add_article(article)
    await db_session.commit()
    persisted = await db_session.get(NewsArticle, article_id)
    assert persisted is not None
    assert persisted.sentiment_confidence == pytest.approx(0.75)
    assert persisted.event_category == "Earnings"
    assert persisted.event_confidence > 0
    assert persisted.driver == "Reported financial performance"
    assert persisted.evidence_excerpt == "Results beat estimates"


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
            SentimentDaily.stock_id == reliance.id,
            SentimentDaily.date == date(2024, 3, 1),
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
async def test_reingest_deduplicates(db_session: AsyncSession, seed_stocks: None) -> None:
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
        make_item(
            "http://x/1", "Reliance Industries surges on strong profit and record growth"
        ),
        make_item(
            "http://x/2", "Reliance Industries falls on weak results and rising losses"
        ),
    ]
    await _service(db_session, items).ingest()

    reliance = await MarketRepository(db_session).get_stock_by_symbol("RELIANCE.NS")
    row = await db_session.scalar(
        select(SentimentDaily).where(SentimentDaily.stock_id == reliance.id)
    )
    assert row.article_count == 2
    assert row.positive_count == 1
    assert row.negative_count == 1


@pytest.mark.asyncio
async def test_latest_universe_sentiment_excludes_stale_rows(
    db_session: AsyncSession, seed_stocks: None
) -> None:
    await _service(
        db_session,
        [
            make_item(
                "http://x/stale",
                "Reliance Industries profit surges to a record high",
            )
        ],
    ).ingest()
    reliance = await MarketRepository(db_session).get_stock_by_symbol("RELIANCE.NS")
    db_session.add(
        DailyPrice(
            stock_id=reliance.id,
            date=date(2024, 3, 20),
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1000,
        )
    )
    await db_session.commit()

    latest = await _service(db_session, []).list_latest_sentiment()
    by_symbol = {row.symbol: row.latest_sentiment for row in latest}
    assert by_symbol["RELIANCE.NS"] is None


def _persisted_article(url: str, title: str, published_at: datetime) -> NewsArticle:
    return NewsArticle(
        source="Legacy Feed",
        url=url,
        fingerprint=(url.encode().hex() + "0" * 64)[:64],
        title=title,
        summary="",
        published_at=published_at,
        sentiment_label="positive",
        sentiment_score=0.5,
        sentiment_positive=0.75,
        sentiment_negative=0.1,
        sentiment_neutral=0.15,
    )


@pytest.mark.asyncio
async def test_ingest_repairs_recently_fetched_stale_story_tags_and_sentiment(
    db_session: AsyncSession, seed_stocks: None
) -> None:
    now = datetime.now(tz=timezone.utc)
    ongc = Stock(symbol="ONGC.NS", name="OIL AND NATURAL GAS CORP.", is_active=True)
    article = _persisted_article(
        "http://legacy/false-oil",
        "Crude oil rises on global tensions",
        datetime(2024, 4, 23, tzinfo=timezone.utc),
    )
    db_session.add_all([ongc, article])
    await db_session.flush()
    db_session.add_all(
        [
            NewsArticleStock(article_id=article.id, stock_id=ongc.id),
            SentimentDaily(
                stock_id=ongc.id,
                date=now.date(),
                avg_sentiment=0.5,
                article_count=1,
                positive_count=1,
                negative_count=0,
                neutral_count=0,
            ),
        ]
    )
    await db_session.commit()

    result = await _service(db_session, []).ingest()

    assert result.new_articles == 0
    assert result.articles_reconciled == 1
    assert result.tags_added == 0
    assert result.tags_removed == 1
    assert await db_session.scalar(select(func.count(NewsArticleStock.id))) == 0
    assert await db_session.scalar(select(func.count(SentimentDaily.id))) == 0
    assert await db_session.scalar(select(func.count(NewsArticle.id))) == 1


@pytest.mark.asyncio
async def test_ingest_adds_missing_tag_to_deduped_recent_article(
    db_session: AsyncSession, seed_stocks: None
) -> None:
    now = datetime.now(tz=timezone.utc)
    article = _persisted_article(
        "http://legacy/missing-reliance",
        "Reliance Industries profit rises strongly",
        now,
    )
    db_session.add(article)
    await db_session.commit()

    result = await _service(db_session, []).ingest()

    reliance = await MarketRepository(db_session).get_stock_by_symbol("RELIANCE.NS")
    link = await db_session.scalar(
        select(NewsArticleStock).where(
            NewsArticleStock.article_id == article.id,
            NewsArticleStock.stock_id == reliance.id,
        )
    )
    sentiment = await db_session.scalar(
        select(SentimentDaily).where(
            SentimentDaily.stock_id == reliance.id,
            SentimentDaily.date == now.date(),
        )
    )
    assert result.articles_reconciled == 1
    assert result.tags_added == 1
    assert result.tags_removed == 0
    assert link is not None
    assert sentiment is not None
    assert sentiment.article_count == 1


@pytest.mark.asyncio
async def test_recent_news_excludes_stale_feed_entries_fetched_today(
    db_session: AsyncSession, seed_stocks: None
) -> None:
    stale = _persisted_article(
        "http://feed/stale",
        "Old quarterly result",
        datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    current = _persisted_article(
        "http://feed/current",
        "Current market session",
        datetime(2024, 3, 1, tzinfo=timezone.utc),
    )
    db_session.add_all([stale, current])
    await db_session.commit()

    result = await _service(db_session, []).list_recent(limit=50)

    assert [article.url for article in result] == ["http://feed/current"]
