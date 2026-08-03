"""Data-access layer for the market domain.

Upserts are done by loading existing rows for a stock once and updating/inserting
in memory (portable across Postgres and SQLite, no dialect-specific ON CONFLICT).
Fine for the modest tracked universe run once per day.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.market.models import DailyPrice, Fundamentals, Indicator, Stock
from app.shared.clients.market_data import FundamentalsData, PriceBar


class MarketRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ----- Stocks ----------------------------------------------------------
    async def upsert_stock(
        self,
        symbol: str,
        *,
        name: str | None,
        sector: str | None,
        industry: str | None,
        exchange: str | None,
    ) -> Stock:
        result = await self.db.execute(select(Stock).where(Stock.symbol == symbol))
        stock = result.scalar_one_or_none()
        if stock is None:
            stock = Stock(symbol=symbol)
            self.db.add(stock)
        # Only overwrite with non-None values so a failed fundamentals fetch
        # doesn't wipe previously-known metadata.
        if name is not None:
            stock.name = name
        if sector is not None:
            stock.sector = sector
        if industry is not None:
            stock.industry = industry
        if exchange is not None:
            stock.exchange = exchange
        await self.db.flush()
        return stock

    async def get_stock_by_symbol(self, symbol: str) -> Stock | None:
        result = await self.db.execute(
            select(Stock)
            .where(Stock.symbol == symbol)
            .options(selectinload(Stock.fundamentals))
        )
        return result.scalar_one_or_none()

    async def get_stock_by_id(self, stock_id: int) -> Stock | None:
        result = await self.db.execute(select(Stock).where(Stock.id == stock_id))
        return result.scalar_one_or_none()

    async def list_active_stocks(self) -> list[Stock]:
        result = await self.db.execute(select(Stock).where(Stock.is_active.is_(True)))
        return list(result.scalars().all())

    async def list_stocks_by_sector(self, sector: str) -> list[Stock]:
        result = await self.db.execute(
            select(Stock).where(Stock.is_active.is_(True), Stock.sector == sector)
        )
        return list(result.scalars().all())

    # ----- Prices ----------------------------------------------------------
    async def upsert_daily_prices(self, stock_id: int, bars: list[PriceBar]) -> int:
        result = await self.db.execute(
            select(DailyPrice).where(DailyPrice.stock_id == stock_id)
        )
        existing = {p.date: p for p in result.scalars().all()}
        for bar in bars:
            row = existing.get(bar.date)
            if row is None:
                self.db.add(
                    DailyPrice(
                        stock_id=stock_id,
                        date=bar.date,
                        open=bar.open,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        volume=bar.volume,
                    )
                )
            else:
                row.open, row.high, row.low, row.close, row.volume = (
                    bar.open,
                    bar.high,
                    bar.low,
                    bar.close,
                    bar.volume,
                )
        await self.db.flush()
        return len(bars)

    async def get_last_two_prices(self, stock_id: int) -> list[DailyPrice]:
        result = await self.db.execute(
            select(DailyPrice)
            .where(DailyPrice.stock_id == stock_id)
            .order_by(DailyPrice.date.desc())
            .limit(2)
        )
        return list(result.scalars().all())

    async def get_price_history(self, stock_id: int) -> list[DailyPrice]:
        result = await self.db.execute(
            select(DailyPrice)
            .where(DailyPrice.stock_id == stock_id)
            .order_by(DailyPrice.date.asc())
        )
        return list(result.scalars().all())

    # ----- Fundamentals ----------------------------------------------------
    async def upsert_fundamentals(self, stock_id: int, data: FundamentalsData) -> None:
        result = await self.db.execute(
            select(Fundamentals).where(Fundamentals.stock_id == stock_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = Fundamentals(stock_id=stock_id)
            self.db.add(row)
        row.market_cap = data.market_cap
        row.pe_ratio = data.pe_ratio
        row.eps = data.eps
        row.dividend_yield = data.dividend_yield
        row.week52_high = data.week52_high
        row.week52_low = data.week52_low
        await self.db.flush()

    # ----- Indicators ------------------------------------------------------
    async def upsert_indicators(
        self, stock_id: int, points: list[dict[str, object]]
    ) -> int:
        result = await self.db.execute(
            select(Indicator).where(Indicator.stock_id == stock_id)
        )
        existing = {i.date: i for i in result.scalars().all()}
        for point in points:
            point_date = point["date"]
            row = existing.get(point_date)  # type: ignore[arg-type]
            if row is None:
                self.db.add(Indicator(stock_id=stock_id, **point))  # type: ignore[arg-type]
            else:
                for key, value in point.items():
                    if key != "date":
                        setattr(row, key, value)
        await self.db.flush()
        return len(points)

    async def get_latest_indicator(self, stock_id: int) -> Indicator | None:
        result = await self.db.execute(
            select(Indicator)
            .where(Indicator.stock_id == stock_id)
            .order_by(Indicator.date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_indicator_history(
        self, stock_id: int, limit: int = 60
    ) -> list[Indicator]:
        result = await self.db.execute(
            select(Indicator)
            .where(Indicator.stock_id == stock_id)
            .order_by(Indicator.date.desc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
        rows.reverse()  # return oldest→newest
        return rows
