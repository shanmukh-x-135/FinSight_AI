"""PostgreSQL concurrency coverage for P10.5 incremental ingestion."""

from __future__ import annotations

import asyncio
import os
import threading
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.market.models import DailyPrice, Stock
from app.market.repository import MarketRepository
from app.market.service import MarketIngestionService
from app.shared.clients.market_data import FundamentalsData, PriceBar
from config.settings import settings

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL, reason="TEST_POSTGRES_URL is required for PostgreSQL integration"
)


class _IncrementalClient:
    def __init__(
        self, bars: list[PriceBar], barrier: threading.Barrier | None = None
    ) -> None:
        self.bars = bars
        self.barrier = barrier
        self.calls: list[tuple[date | None, date | None]] = []

    def fetch_daily_prices(
        self,
        _symbol: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[PriceBar]:
        self.calls.append((start_date, end_date))
        if self.barrier is not None:
            self.barrier.wait(timeout=5)
        return self.bars

    def fetch_fundamentals(self, _symbol: str) -> FundamentalsData:
        raise AssertionError("incremental mode must not refetch fundamentals")


@pytest.mark.asyncio
async def test_postgres_concurrent_incremental_workers_share_one_window_and_row() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_size=6)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    symbol = f"P10INC-{uuid4().hex[:10]}.NS"
    first_day = date(2099, 1, 1)
    latest_day = first_day + timedelta(days=59)
    target = latest_day + timedelta(days=1)
    synchronized_at = datetime(2099, 3, 1, tzinfo=timezone.utc)
    initial = [
        PriceBar(
            first_day + timedelta(days=i),
            100 + i,
            102 + i,
            99 + i,
            101 + i,
            1000 + i,
        )
        for i in range(60)
    ]
    new_bar = PriceBar(target, 200, 202, 199, 201, 2000)
    future_bar = PriceBar(target + timedelta(days=1), 300, 302, 299, 301, 3000)
    provider_barrier = threading.Barrier(2)
    clients = [
        _IncrementalClient([new_bar, future_bar], provider_barrier)
        for _ in range(2)
    ]

    try:
        async with factory() as db:
            repo = MarketRepository(db)
            stock = await repo.upsert_stock(
                symbol,
                name="P10 Incremental",
                sector="Test",
                industry=None,
                exchange="NSE",
            )
            await repo.upsert_daily_prices(stock.id, initial)
            await repo.mark_full_price_sync(stock.id, synchronized_at)
            await db.commit()

        async def ingest(client: _IncrementalClient):
            async with factory() as db:
                return await MarketIngestionService(db, client).ingest(
                    [symbol],
                    target_trading_date=target,
                    now=synchronized_at + timedelta(days=1),
                )

        results = await asyncio.gather(*(ingest(client) for client in clients))
        assert all(result.incremental_symbols == 1 for result in results)
        expected_window = (
            latest_day - timedelta(days=settings.market_incremental_overlap_days),
            target + timedelta(days=1),
        )
        assert all(client.calls == [expected_window] for client in clients)

        async with factory() as db:
            stock_id = await db.scalar(select(Stock.id).where(Stock.symbol == symbol))
            assert stock_id is not None
            assert await db.scalar(
                select(func.count(DailyPrice.id)).where(
                    DailyPrice.stock_id == stock_id,
                    DailyPrice.date == target,
                )
            ) == 1
            assert await db.scalar(
                select(func.count(DailyPrice.id)).where(
                    DailyPrice.stock_id == stock_id,
                    DailyPrice.date == future_bar.date,
                )
            ) == 0
    finally:
        async with factory.begin() as db:
            await db.execute(delete(Stock).where(Stock.symbol == symbol))
        await engine.dispose()
