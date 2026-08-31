"""Seeded market data for the dashboard-summary tests.

Mirrors the intelligence seed (self-contained so the fixture resolves without
cross-package imports): 3 stocks — AAA bullish, BBB bearish, CCC neutral.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.models import DailyPrice, Indicator, Stock
from app.news.models import NewsArticle, NewsArticleStock, SentimentDaily

D1, D2 = date(2024, 1, 1), date(2024, 1, 2)


@pytest_asyncio.fixture
async def seed_market(db_session: AsyncSession) -> dict[str, int]:
    specs = [
        # symbol, sector, prev, last, rsi, ema20, ema50, macd, atr, sentiment
        ("AAA.NS", "Technology", 100, 110, 65, 105, 100, 1.5, 2.2, 0.4),
        ("BBB.NS", "Energy", 100, 90, 35, 95, 100, -1.2, 3.0, -0.3),
        ("CCC.NS", "Technology", 50, 50, 50, 50, 50, 0.0, 0.5, None),
    ]
    ids: dict[str, int] = {}
    for symbol, sector, prev, last, rsi, ema20, ema50, macd, atr, senti in specs:
        stock = Stock(symbol=symbol, name=symbol.split(".")[0], sector=sector, exchange="NSE")
        db_session.add(stock)
        await db_session.flush()
        ids[symbol] = stock.id
        db_session.add_all([
            DailyPrice(stock_id=stock.id, date=D1, open=prev, high=prev, low=prev, close=prev, volume=1000),
            DailyPrice(stock_id=stock.id, date=D2, open=last, high=last, low=last, close=last, volume=1000),
            Indicator(stock_id=stock.id, date=D2, rsi_14=rsi, ema_20=ema20, ema_50=ema50,
                      macd_histogram=macd, atr_14=atr),
        ])
        if senti is not None:
            label = "positive" if senti > 0 else "negative"
            article = NewsArticle(
                source="Fixture Feed",
                url=f"https://example.test/{symbol}",
                fingerprint=f"{stock.id:064x}",
                title=f"Verified coverage for {symbol}",
                summary="Controlled dashboard fixture",
                published_at=datetime(2024, 1, 2, 10, tzinfo=timezone.utc),
                sentiment_label=label,
                sentiment_score=senti,
                sentiment_positive=max(senti, 0),
                sentiment_negative=max(-senti, 0),
                sentiment_neutral=1 - abs(senti),
                sentiment_confidence=0.7,
                event_category="Other",
                event_confidence=0.35,
                driver="Unclassified company coverage",
                evidence_excerpt="Controlled dashboard fixture",
            )
            db_session.add(article)
            await db_session.flush()
            db_session.add(
                NewsArticleStock(
                    article_id=article.id,
                    stock_id=stock.id,
                    matching_alias=symbol.split(".")[0],
                    entity_match_confidence=0.9,
                )
            )
            db_session.add(SentimentDaily(
                stock_id=stock.id, date=D2, avg_sentiment=senti, article_count=1,
                positive_count=1 if senti > 0 else 0, negative_count=1 if senti < 0 else 0,
                neutral_count=0,
            ))
    await db_session.commit()
    return ids
