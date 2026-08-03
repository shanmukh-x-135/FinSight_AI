"""Data-access for the portfolio domain.

Every read/write that touches a user-owned resource is scoped by ``user_id``
(directly for portfolios/watchlist, or via a pre-verified portfolio for
holdings) so a request can never reach another user's data.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.portfolio.models import Portfolio, PortfolioItem, WatchlistItem


class PortfolioRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ----- Portfolios (user-scoped) ---------------------------------------
    async def create_portfolio(self, user_id: int, name: str) -> Portfolio:
        portfolio = Portfolio(user_id=user_id, name=name)
        self.db.add(portfolio)
        await self.db.flush()
        return portfolio

    async def get_portfolio(self, user_id: int, portfolio_id: int) -> Portfolio | None:
        result = await self.db.execute(
            select(Portfolio)
            .where(Portfolio.id == portfolio_id, Portfolio.user_id == user_id)
            .options(selectinload(Portfolio.items))
        )
        return result.scalar_one_or_none()

    async def list_portfolios(self, user_id: int) -> list[Portfolio]:
        result = await self.db.execute(
            select(Portfolio)
            .where(Portfolio.user_id == user_id)
            .options(selectinload(Portfolio.items))
            .order_by(Portfolio.created_at.asc())
        )
        return list(result.scalars().all())

    async def delete_portfolio(self, portfolio: Portfolio) -> None:
        await self.db.delete(portfolio)
        await self.db.flush()

    # ----- Holdings (scoped via an already-verified portfolio) ------------
    async def get_holding(self, portfolio_id: int, item_id: int) -> PortfolioItem | None:
        result = await self.db.execute(
            select(PortfolioItem).where(
                PortfolioItem.id == item_id,
                PortfolioItem.portfolio_id == portfolio_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_holding_by_stock(
        self, portfolio_id: int, stock_id: int
    ) -> PortfolioItem | None:
        result = await self.db.execute(
            select(PortfolioItem).where(
                PortfolioItem.portfolio_id == portfolio_id,
                PortfolioItem.stock_id == stock_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_holding(
        self, portfolio_id: int, stock_id: int, quantity: float, avg_buy_price: float
    ) -> PortfolioItem:
        item = PortfolioItem(
            portfolio_id=portfolio_id,
            stock_id=stock_id,
            quantity=quantity,
            avg_buy_price=avg_buy_price,
        )
        self.db.add(item)
        await self.db.flush()
        return item

    async def delete_holding(self, item: PortfolioItem) -> None:
        await self.db.delete(item)
        await self.db.flush()

    # ----- Watchlist (user-scoped) ----------------------------------------
    async def list_watchlist(self, user_id: int) -> list[WatchlistItem]:
        result = await self.db.execute(
            select(WatchlistItem)
            .where(WatchlistItem.user_id == user_id)
            .order_by(
                WatchlistItem.pinned.desc(),
                WatchlistItem.sort_order.asc(),
                WatchlistItem.created_at.asc(),
            )
        )
        return list(result.scalars().all())

    async def get_watchlist_item(
        self, user_id: int, item_id: int
    ) -> WatchlistItem | None:
        result = await self.db.execute(
            select(WatchlistItem).where(
                WatchlistItem.id == item_id, WatchlistItem.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def get_watchlist_item_by_stock(
        self, user_id: int, stock_id: int
    ) -> WatchlistItem | None:
        result = await self.db.execute(
            select(WatchlistItem).where(
                WatchlistItem.user_id == user_id, WatchlistItem.stock_id == stock_id
            )
        )
        return result.scalar_one_or_none()

    async def add_watchlist_item(
        self, user_id: int, stock_id: int, pinned: bool
    ) -> WatchlistItem:
        item = WatchlistItem(user_id=user_id, stock_id=stock_id, pinned=pinned)
        self.db.add(item)
        await self.db.flush()
        return item

    async def delete_watchlist_item(self, item: WatchlistItem) -> None:
        await self.db.delete(item)
        await self.db.flush()
