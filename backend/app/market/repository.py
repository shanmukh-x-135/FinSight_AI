"""Data-access layer for the market domain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.market.models import DailyPrice, Fundamentals, Indicator, Stock
from app.shared.clients.market_data import FundamentalsData, PriceBar
from app.shared.upsert import conflict_insert


@dataclass(frozen=True)
class MarketSnapshot:
    stock: Stock
    prices: tuple[DailyPrice, ...]
    indicator: Indicator | None


@dataclass(frozen=True)
class PriceIngestionState:
    stock_id: int
    latest_price_date: date | None
    last_full_price_sync_at: datetime | None


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
        is_active: bool | None = None,
    ) -> Stock:
        # Only overwrite with non-None values so a failed fundamentals fetch
        # doesn't wipe previously-known metadata.
        values: dict[str, object] = {"symbol": symbol}
        if name is not None:
            values["name"] = name
        if sector is not None:
            values["sector"] = sector
        if industry is not None:
            values["industry"] = industry
        if exchange is not None:
            values["exchange"] = exchange
        if is_active is not None:
            values["is_active"] = is_active
        stmt = conflict_insert(self.db, Stock).values(**values)
        updates = {key: getattr(stmt.excluded, key) for key in values if key != "symbol"}
        # A symbol-only call remains a harmless atomic no-op on conflict.
        if not updates:
            updates = {"symbol": stmt.excluded.symbol}
        result = await self.db.execute(
            stmt.on_conflict_do_update(
                index_elements=[Stock.symbol], set_=updates
            )
            .returning(Stock)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one()

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

    async def get_stocks_by_ids(self, stock_ids: Iterable[int]) -> dict[int, Stock]:
        ids = list(dict.fromkeys(stock_ids))
        if not ids:
            return {}
        result = await self.db.execute(select(Stock).where(Stock.id.in_(ids)))
        return {stock.id: stock for stock in result.scalars()}

    async def list_active_stocks(self) -> list[Stock]:
        result = await self.db.execute(select(Stock).where(Stock.is_active.is_(True)))
        return list(result.scalars().all())

    async def get_market_snapshots(
        self,
        stock_ids: Iterable[int],
        *,
        known_stocks: Iterable[Stock] | None = None,
    ) -> dict[int, MarketSnapshot]:
        """Load metadata, latest two prices, and latest indicator in ≤3 queries."""
        ids = list(dict.fromkeys(stock_ids))
        if not ids:
            return {}

        if known_stocks is None:
            stocks = list((await self.get_stocks_by_ids(ids)).values())
        else:
            id_set = set(ids)
            stocks = [stock for stock in known_stocks if stock.id in id_set]

        price_partition = (
            select(
                DailyPrice,
                func.row_number()
                .over(
                    partition_by=DailyPrice.stock_id,
                    order_by=DailyPrice.date.desc(),
                )
                .label("row_number"),
            )
            .where(DailyPrice.stock_id.in_(ids))
            .subquery()
        )
        latest_price = aliased(DailyPrice, price_partition)
        price_result = await self.db.execute(
            select(latest_price)
            .where(price_partition.c.row_number <= 2)
            .order_by(latest_price.stock_id, latest_price.date.desc())
        )
        prices_by_stock: dict[int, list[DailyPrice]] = {}
        for price in price_result.scalars():
            prices_by_stock.setdefault(price.stock_id, []).append(price)

        indicator_partition = (
            select(
                Indicator,
                func.row_number()
                .over(
                    partition_by=Indicator.stock_id,
                    order_by=Indicator.date.desc(),
                )
                .label("row_number"),
            )
            .where(Indicator.stock_id.in_(ids))
            .subquery()
        )
        latest_indicator = aliased(Indicator, indicator_partition)
        indicator_result = await self.db.execute(
            select(latest_indicator).where(indicator_partition.c.row_number == 1)
        )
        indicators = {
            indicator.stock_id: indicator for indicator in indicator_result.scalars()
        }

        return {
            stock.id: MarketSnapshot(
                stock=stock,
                prices=tuple(prices_by_stock.get(stock.id, [])),
                indicator=indicators.get(stock.id),
            )
            for stock in stocks
        }

    async def list_stocks_by_sector(self, sector: str) -> list[Stock]:
        result = await self.db.execute(
            select(Stock).where(Stock.is_active.is_(True), Stock.sector == sector)
        )
        return list(result.scalars().all())

    async def get_price_ingestion_state(
        self, symbol: str
    ) -> PriceIngestionState | None:
        """Return the per-symbol watermark without loading its price history."""
        result = await self.db.execute(
            select(
                Stock.id,
                func.max(DailyPrice.date),
                Stock.last_full_price_sync_at,
            )
            .outerjoin(DailyPrice, DailyPrice.stock_id == Stock.id)
            .where(Stock.symbol == symbol)
            .group_by(Stock.id, Stock.last_full_price_sync_at)
        )
        row = result.one_or_none()
        if row is None:
            return None
        return PriceIngestionState(
            stock_id=row[0],
            latest_price_date=row[1],
            last_full_price_sync_at=row[2],
        )

    async def mark_full_price_sync(
        self, stock_id: int, synchronized_at: datetime
    ) -> None:
        await self.db.execute(
            update(Stock)
            .where(Stock.id == stock_id)
            .values(last_full_price_sync_at=synchronized_at)
        )

    # ----- Prices ----------------------------------------------------------
    async def upsert_daily_prices(self, stock_id: int, bars: list[PriceBar]) -> int:
        unique_bars = {bar.date: bar for bar in bars}
        if not unique_bars:
            return 0
        values = [
            {
                "stock_id": stock_id,
                "date": bar.date,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in unique_bars.values()
        ]
        stmt = conflict_insert(self.db, DailyPrice).values(values)
        result = await self.db.execute(
            stmt.on_conflict_do_update(
                index_elements=[DailyPrice.stock_id, DailyPrice.date],
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                },
            )
            .returning(DailyPrice)
            .execution_options(populate_existing=True)
        )
        result.scalars().all()
        return len(unique_bars)

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
        values = {
            name: value
            for name, value in {
                "market_cap": data.market_cap,
                "pe_ratio": data.pe_ratio,
                "eps": data.eps,
                "dividend_yield": data.dividend_yield,
                "week52_high": data.week52_high,
                "week52_low": data.week52_low,
            }.items()
            if value is not None
        }
        if not values:
            return
        stmt = conflict_insert(self.db, Fundamentals).values(
            stock_id=stock_id, **values
        )
        result = await self.db.execute(
            stmt.on_conflict_do_update(
                index_elements=[Fundamentals.stock_id],
                set_={
                    **{name: getattr(stmt.excluded, name) for name in values},
                    "updated_at": func.now(),
                },
            )
            .returning(Fundamentals)
            .execution_options(populate_existing=True)
        )
        result.scalars().all()

    # ----- Indicators ------------------------------------------------------
    async def upsert_indicators(
        self, stock_id: int, points: list[dict[str, object]]
    ) -> int:
        unique_points = {point["date"]: point for point in points}
        if not unique_points:
            return 0
        values = [{"stock_id": stock_id, **point} for point in unique_points.values()]
        stmt = conflict_insert(self.db, Indicator).values(values)
        update_columns = (
            "rsi_14",
            "ema_20",
            "ema_50",
            "macd",
            "macd_signal",
            "macd_histogram",
            "bb_upper",
            "bb_middle",
            "bb_lower",
            "atr_14",
        )
        result = await self.db.execute(
            stmt.on_conflict_do_update(
                index_elements=[Indicator.stock_id, Indicator.date],
                set_={name: getattr(stmt.excluded, name) for name in update_columns},
            )
            .returning(Indicator)
            .execution_options(populate_existing=True)
        )
        result.scalars().all()
        return len(unique_points)

    async def get_latest_indicator(self, stock_id: int) -> Indicator | None:
        result = await self.db.execute(
            select(Indicator)
            .where(Indicator.stock_id == stock_id)
            .order_by(Indicator.date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_latest_indicators_with_close(
        self,
    ) -> list[tuple[Indicator, float | None]]:
        latest = (
            select(
                Indicator.stock_id.label("stock_id"),
                func.max(Indicator.date).label("latest_date"),
            )
            .group_by(Indicator.stock_id)
            .subquery()
        )
        result = await self.db.execute(
            select(Indicator, DailyPrice.close)
            .join(
                latest,
                and_(
                    Indicator.stock_id == latest.c.stock_id,
                    Indicator.date == latest.c.latest_date,
                ),
            )
            .join(Stock, Stock.id == Indicator.stock_id)
            .outerjoin(
                DailyPrice,
                and_(
                    DailyPrice.stock_id == Indicator.stock_id,
                    DailyPrice.date == Indicator.date,
                ),
            )
            .where(Stock.is_active.is_(True))
        )
        return [(indicator, close) for indicator, close in result.all()]

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
