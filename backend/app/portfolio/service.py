"""Portfolio & watchlist business logic.

Owns ownership enforcement, holding/stock resolution, and assembly of the pure
analytics inputs from Phase 2 market data. Deterministic — no AI.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.market.repository import MarketRepository
from app.portfolio.analytics import HoldingInput, compute_portfolio_analytics
from app.portfolio.constants import DEFAULT_PORTFOLIO_NAME
from app.portfolio.exceptions import (
    DuplicateHoldingError,
    DuplicateWatchlistItemError,
    HoldingNotFoundError,
    PortfolioNotFoundError,
    StockNotTrackedError,
    WatchlistItemNotFoundError,
)
from app.portfolio.models import Portfolio, PortfolioItem, WatchlistItem
from app.portfolio.repository import PortfolioRepository
from app.portfolio.schemas import (
    HoldingCreate,
    HoldingOut,
    HoldingUpdate,
    PortfolioAnalyticsOut,
    PortfolioDetailOut,
    PortfolioSummaryOut,
    WatchlistItemOut,
    WatchlistUpdate,
)


class PortfolioService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = PortfolioRepository(db)
        self.market = MarketRepository(db)

    # ----- helpers ---------------------------------------------------------
    async def _owned_portfolio(self, user_id: int, portfolio_id: int) -> Portfolio:
        portfolio = await self.repo.get_portfolio(user_id, portfolio_id)
        if portfolio is None:
            raise PortfolioNotFoundError()
        return portfolio

    async def _resolve_stock_id(self, symbol: str) -> int:
        stock = await self.market.get_stock_by_symbol(symbol)
        if stock is None:
            raise StockNotTrackedError(symbol)
        return stock.id

    # ----- Portfolio CRUD --------------------------------------------------
    async def create_portfolio(self, user_id: int, name: str | None) -> Portfolio:
        portfolio = await self.repo.create_portfolio(
            user_id, name or DEFAULT_PORTFOLIO_NAME
        )
        await self.db.commit()
        return portfolio

    async def list_portfolios(self, user_id: int) -> list[PortfolioSummaryOut]:
        portfolios = await self.repo.list_portfolios(user_id)
        return [
            PortfolioSummaryOut(
                id=p.id, name=p.name, created_at=p.created_at, holding_count=len(p.items)
            )
            for p in portfolios
        ]

    async def get_portfolio_detail(
        self, user_id: int, portfolio_id: int
    ) -> PortfolioDetailOut:
        portfolio = await self._owned_portfolio(user_id, portfolio_id)
        holdings = []
        for item in portfolio.items:
            stock = await self.market.get_stock_by_id(item.stock_id)
            holdings.append(
                HoldingOut(
                    id=item.id,
                    symbol=stock.symbol if stock else "",
                    name=stock.name if stock else None,
                    sector=stock.sector if stock else None,
                    quantity=item.quantity,
                    avg_buy_price=item.avg_buy_price,
                )
            )
        return PortfolioDetailOut(
            id=portfolio.id,
            name=portfolio.name,
            created_at=portfolio.created_at,
            holdings=holdings,
        )

    async def rename_portfolio(
        self, user_id: int, portfolio_id: int, name: str
    ) -> Portfolio:
        portfolio = await self._owned_portfolio(user_id, portfolio_id)
        portfolio.name = name
        await self.db.commit()
        return portfolio

    async def delete_portfolio(self, user_id: int, portfolio_id: int) -> None:
        portfolio = await self._owned_portfolio(user_id, portfolio_id)
        await self.repo.delete_portfolio(portfolio)
        await self.db.commit()

    # ----- Holdings --------------------------------------------------------
    async def add_holding(
        self, user_id: int, portfolio_id: int, payload: HoldingCreate
    ) -> PortfolioItem:
        await self._owned_portfolio(user_id, portfolio_id)
        stock_id = await self._resolve_stock_id(payload.symbol)
        if await self.repo.get_holding_by_stock(portfolio_id, stock_id) is not None:
            raise DuplicateHoldingError(payload.symbol)
        item = await self.repo.add_holding(
            portfolio_id, stock_id, payload.quantity, payload.avg_buy_price
        )
        await self.db.commit()
        return item

    async def update_holding(
        self, user_id: int, portfolio_id: int, item_id: int, payload: HoldingUpdate
    ) -> PortfolioItem:
        await self._owned_portfolio(user_id, portfolio_id)
        item = await self.repo.get_holding(portfolio_id, item_id)
        if item is None:
            raise HoldingNotFoundError()
        if payload.quantity is not None:
            item.quantity = payload.quantity
        if payload.avg_buy_price is not None:
            item.avg_buy_price = payload.avg_buy_price
        await self.db.commit()
        return item

    async def remove_holding(
        self, user_id: int, portfolio_id: int, item_id: int
    ) -> None:
        await self._owned_portfolio(user_id, portfolio_id)
        item = await self.repo.get_holding(portfolio_id, item_id)
        if item is None:
            raise HoldingNotFoundError()
        await self.repo.delete_holding(item)
        await self.db.commit()

    # ----- Analytics -------------------------------------------------------
    async def get_analytics(
        self, user_id: int, portfolio_id: int
    ) -> PortfolioAnalyticsOut:
        portfolio = await self._owned_portfolio(user_id, portfolio_id)
        inputs: list[HoldingInput] = []
        for item in portfolio.items:
            stock = await self.market.get_stock_by_id(item.stock_id)
            prices = await self.market.get_last_two_prices(item.stock_id)
            latest = prices[0] if prices else None
            previous = prices[1] if len(prices) > 1 else None
            indicator = await self.market.get_latest_indicator(item.stock_id)
            inputs.append(
                HoldingInput(
                    id=item.id,
                    symbol=stock.symbol if stock else "",
                    name=stock.name if stock else None,
                    sector=stock.sector if stock else None,
                    quantity=item.quantity,
                    avg_buy_price=item.avg_buy_price,
                    current_price=latest.close if latest else None,
                    previous_close=previous.close if previous else None,
                    atr=indicator.atr_14 if indicator else None,
                )
            )
        return compute_portfolio_analytics(portfolio.id, portfolio.name, inputs)

    # ----- Watchlist -------------------------------------------------------
    async def list_watchlist(self, user_id: int) -> list[WatchlistItemOut]:
        items = await self.repo.list_watchlist(user_id)
        out: list[WatchlistItemOut] = []
        for item in items:
            stock = await self.market.get_stock_by_id(item.stock_id)
            prices = await self.market.get_last_two_prices(item.stock_id)
            latest = prices[0] if prices else None
            previous = prices[1] if len(prices) > 1 else None
            change = change_pct = None
            if latest and previous and previous.close:
                change = latest.close - previous.close
                change_pct = change / previous.close * 100.0
            out.append(
                WatchlistItemOut(
                    id=item.id,
                    symbol=stock.symbol if stock else "",
                    name=stock.name if stock else None,
                    sector=stock.sector if stock else None,
                    current_price=latest.close if latest else None,
                    previous_close=previous.close if previous else None,
                    change=change,
                    change_percent=change_pct,
                    pinned=item.pinned,
                    sort_order=item.sort_order,
                )
            )
        return out

    async def add_watchlist_item(
        self, user_id: int, symbol: str, pinned: bool
    ) -> WatchlistItem:
        stock_id = await self._resolve_stock_id(symbol)
        if await self.repo.get_watchlist_item_by_stock(user_id, stock_id) is not None:
            raise DuplicateWatchlistItemError(symbol)
        item = await self.repo.add_watchlist_item(user_id, stock_id, pinned)
        await self.db.commit()
        return item

    async def update_watchlist_item(
        self, user_id: int, item_id: int, payload: WatchlistUpdate
    ) -> WatchlistItem:
        item = await self.repo.get_watchlist_item(user_id, item_id)
        if item is None:
            raise WatchlistItemNotFoundError()
        if payload.pinned is not None:
            item.pinned = payload.pinned
        if payload.sort_order is not None:
            item.sort_order = payload.sort_order
        await self.db.commit()
        return item

    async def remove_watchlist_item(self, user_id: int, item_id: int) -> None:
        item = await self.repo.get_watchlist_item(user_id, item_id)
        if item is None:
            raise WatchlistItemNotFoundError()
        await self.repo.delete_watchlist_item(item)
        await self.db.commit()
