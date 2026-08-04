"""Regression tests for bounded-query market snapshot assembly."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.models import DailyPrice, Indicator, Stock
from app.market.repository import MarketRepository


@pytest.mark.asyncio
async def test_market_snapshots_use_constant_query_count(
    db_session: AsyncSession,
) -> None:
    stocks = [Stock(symbol=f"S{i}.NS", is_active=True) for i in range(3)]
    db_session.add_all(stocks)
    await db_session.flush()
    for stock in stocks:
        db_session.add_all(
            [
                DailyPrice(
                    stock_id=stock.id,
                    date=date(2026, 8, day),
                    open=100,
                    high=102,
                    low=99,
                    close=100 + day,
                    volume=1000,
                )
                for day in (1, 2, 3)
            ]
        )
        db_session.add(
            Indicator(stock_id=stock.id, date=date(2026, 8, 3), rsi_14=50 + stock.id)
        )
    await db_session.commit()

    engine = db_session.bind
    assert engine is not None
    statements: list[str] = []

    def count_statement(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", count_statement)
    try:
        snapshots = await MarketRepository(db_session).get_market_snapshots(
            stock.id for stock in stocks
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_statement)

    assert len(statements) == 3  # stocks + latest-two prices + latest indicators
    assert set(snapshots) == {stock.id for stock in stocks}
    assert all(len(snapshot.prices) == 2 for snapshot in snapshots.values())
    assert all(snapshot.prices[0].date == date(2026, 8, 3) for snapshot in snapshots.values())
    assert all(snapshot.indicator is not None for snapshot in snapshots.values())
