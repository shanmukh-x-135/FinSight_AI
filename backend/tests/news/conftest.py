"""Shared fixtures for news tests: a fake news client and seeded stocks."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.models import DailyPrice, Stock
from app.shared.clients.news_client import NewsItem

PUB = datetime(2024, 3, 1, 10, 0, tzinfo=timezone.utc)


def make_item(url: str, title: str, summary: str = "", published_at=PUB) -> NewsItem:
    return NewsItem(
        source="Test Feed",
        url=url,
        title=title,
        summary=summary,
        published_at=published_at,
    )


class FakeNewsClient:
    """Returns a fixed list of items (no network)."""

    def __init__(self, items: list[NewsItem]) -> None:
        self.items = items

    def fetch(self) -> list[NewsItem]:
        return self.items


@pytest_asyncio.fixture
async def seed_stocks(db_session: AsyncSession) -> None:
    db_session.add_all(
        [
            Stock(
                symbol="RELIANCE.NS",
                name="RELIANCE INDUSTRIES LTD",
                sector="Energy",
                exchange="NSE",
            ),
            Stock(
                symbol="TCS.NS",
                name="Tata Consultancy Services",
                sector="Technology",
                exchange="NSE",
            ),
        ]
    )
    await db_session.flush()
    stocks = (await db_session.execute(select(Stock))).scalars().all()
    db_session.add_all(
        [
            DailyPrice(
                stock_id=stock.id,
                date=date(2024, 3, 1),
                open=100,
                high=101,
                low=99,
                close=100,
                volume=1000,
            )
            for stock in stocks
        ]
    )
    await db_session.commit()
