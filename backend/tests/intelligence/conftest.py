"""Seeded market data for intelligence (report/recommendation) tests."""

from __future__ import annotations

from datetime import date

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.models import DailyPrice, Indicator, Stock
from app.news.models import SentimentDaily

D1, D2 = date(2024, 1, 1), date(2024, 1, 2)


@pytest_asyncio.fixture
async def seed_market(db_session: AsyncSession) -> dict[str, int]:
    """3 stocks: AAA bullish, BBB bearish, CCC neutral. Returns symbol→stock_id."""
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
            db_session.add(SentimentDaily(
                stock_id=stock.id, date=D2, avg_sentiment=senti, article_count=1,
                positive_count=1 if senti > 0 else 0, negative_count=1 if senti < 0 else 0,
                neutral_count=0,
            ))
    await db_session.commit()
    return ids
