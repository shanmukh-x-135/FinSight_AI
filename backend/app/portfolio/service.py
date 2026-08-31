"""Portfolio & watchlist business logic.

Owns ownership enforcement, holding/stock resolution, and assembly of the pure
analytics inputs from Phase 2 market data. Deterministic — no AI.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.history.models import HistoricalSession
from app.market.models import Stock
from app.market.repository import MarketRepository
from app.market.signals import trend_signal
from app.portfolio.analytics import HoldingInput, compute_portfolio_analytics
from app.portfolio.constants import DEFAULT_PORTFOLIO_NAME
from app.portfolio.exceptions import (
    CounterfactualError,
    DuplicateHoldingError,
    DuplicateWatchlistItemError,
    HoldingNotFoundError,
    PortfolioNotFoundError,
    StockNotTrackedError,
    WatchlistItemNotFoundError,
)
from app.portfolio.models import Portfolio, PortfolioItem, WatchlistItem
from app.portfolio.repository import PortfolioRepository
from app.portfolio.risk import RiskHoldingInput, compute_portfolio_risk
from app.portfolio.schemas import (
    CounterfactualOut,
    CounterfactualRequest,
    HoldingCreate,
    HoldingOut,
    HoldingUpdate,
    PortfolioAnalyticsOut,
    PortfolioDetailOut,
    PortfolioRiskOut,
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
        stocks = await self.market.get_stocks_by_ids(
            item.stock_id for item in portfolio.items
        )
        holdings = []
        for item in portfolio.items:
            stock = stocks.get(item.stock_id)
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

    async def remove_holding(self, user_id: int, portfolio_id: int, item_id: int) -> None:
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
        snapshots = await self.market.get_market_snapshots(
            item.stock_id for item in portfolio.items
        )
        inputs: list[HoldingInput] = []
        for item in portfolio.items:
            snapshot = snapshots.get(item.stock_id)
            stock = snapshot.stock if snapshot else None
            prices = snapshot.prices if snapshot else ()
            indicator = snapshot.indicator if snapshot else None
            latest = prices[0] if prices else None
            previous = prices[1] if len(prices) > 1 else None
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

    async def _benchmark_sector_weights(self) -> dict[str, float]:
        constituents = await self.market.list_approved_equities("NIFTY100")
        if not constituents:
            return {}
        caps = {
            stock.id: (
                stock.fundamentals.market_cap
                if stock.fundamentals and stock.fundamentals.market_cap
                else None
            )
            for stock in constituents
        }
        total_cap = sum(value for value in caps.values() if value is not None)
        complete_caps = total_cap > 0 and all(value is not None for value in caps.values())
        sector_weights: dict[str, float] = {}
        for stock in constituents:
            weight = (
                caps[stock.id] / total_cap
                if complete_caps and caps[stock.id] is not None
                else 1 / len(constituents)
            )
            sector = stock.sector or "Unknown"
            sector_weights[sector] = sector_weights.get(sector, 0.0) + weight * 100
        return sector_weights

    async def _risk_for_quantities(
        self,
        portfolio_id: int,
        quantities: dict[int, float],
        stocks: dict[int, Stock],
    ) -> PortfolioRiskOut:
        benchmark = await self.market.get_stock_by_symbol("^NSEI")
        ids = [stock_id for stock_id, quantity in quantities.items() if quantity > 0]
        history_ids = [*ids, *([benchmark.id] if benchmark else [])]
        histories = await self.market.get_price_histories(history_ids, limit=300)
        holdings = []
        for stock_id in ids:
            stock = stocks[stock_id]
            prices = histories.get(stock_id, [])
            holdings.append(
                RiskHoldingInput(
                    symbol=stock.symbol,
                    sector=stock.sector or "Unknown",
                    quantity=quantities[stock_id],
                    current_price=prices[-1].close if prices else None,
                    closes=tuple((row.date, row.close) for row in prices),
                )
            )
        all_dates = [day for holding in holdings for day, _ in holding.closes]
        regime_result = (
            await self.db.execute(
                select(HistoricalSession.date, HistoricalSession.pct_advancers).where(
                    HistoricalSession.date >= min(all_dates),
                    HistoricalSession.date <= max(all_dates),
                    HistoricalSession.feature_version == "market_regime_v1",
                )
            )
            if all_dates
            else None
        )
        regimes = {
            day: (
                "broad_positive"
                if breadth >= 0.60
                else "broad_negative"
                if breadth <= 0.40
                else "mixed"
            )
            for day, breadth in (regime_result.all() if regime_result else [])
        }
        benchmark_prices = histories.get(benchmark.id, []) if benchmark else []
        return compute_portfolio_risk(
            portfolio_id,
            holdings,
            tuple((row.date, row.close) for row in benchmark_prices),
            await self._benchmark_sector_weights(),
            regimes,
        )

    async def get_risk(self, user_id: int, portfolio_id: int) -> PortfolioRiskOut:
        portfolio = await self._owned_portfolio(user_id, portfolio_id)
        stocks = await self.market.get_stocks_by_ids(
            item.stock_id for item in portfolio.items
        )
        return await self._risk_for_quantities(
            portfolio.id,
            {item.stock_id: item.quantity for item in portfolio.items},
            stocks,
        )

    async def counterfactual(
        self,
        user_id: int,
        portfolio_id: int,
        payload: CounterfactualRequest,
    ) -> CounterfactualOut:
        portfolio = await self._owned_portfolio(user_id, portfolio_id)
        stocks = await self.market.get_stocks_by_ids(
            item.stock_id for item in portfolio.items
        )
        before_quantities = {item.stock_id: item.quantity for item in portfolio.items}
        after_quantities = dict(before_quantities)
        normalized: dict[str, float] = {}
        for change in payload.changes:
            symbol = change.symbol.strip().upper()
            normalized[symbol] = normalized.get(symbol, 0.0) + change.quantity_delta
        for symbol, delta in normalized.items():
            stock = await self.market.get_stock_by_symbol(symbol)
            if stock is None:
                raise CounterfactualError(f"Stock '{symbol}' is not tracked.")
            stocks[stock.id] = stock
            quantity = after_quantities.get(stock.id, 0.0) + delta
            if quantity < 0:
                raise CounterfactualError(
                    f"The {symbol} change would create a negative quantity."
                )
            after_quantities[stock.id] = quantity
        if not any(quantity > 0 for quantity in after_quantities.values()):
            raise CounterfactualError("A scenario must retain at least one holding.")
        before = await self._risk_for_quantities(portfolio.id, before_quantities, stocks)
        after = await self._risk_for_quantities(portfolio.id, after_quantities, stocks)

        def delta(after_value: float | None, before_value: float | None) -> float | None:
            return (
                round(after_value - before_value, 6)
                if after_value is not None and before_value is not None
                else None
            )

        return CounterfactualOut(
            changes=payload.changes,
            before=before,
            after=after,
            deltas={
                "annualized_volatility_percent": delta(
                    after.annualized_volatility_percent,
                    before.annualized_volatility_percent,
                ),
                "beta": delta(after.beta, before.beta),
                "max_drawdown_percent": delta(
                    after.max_drawdown_percent, before.max_drawdown_percent
                ),
                "concentration_hhi": delta(
                    after.concentration_hhi, before.concentration_hhi
                ),
                "momentum_exposure_percent": delta(
                    after.momentum_exposure_percent,
                    before.momentum_exposure_percent,
                ),
            },
        )

    # ----- Watchlist -------------------------------------------------------
    async def list_watchlist(self, user_id: int) -> list[WatchlistItemOut]:
        items = await self.repo.list_watchlist(user_id)
        snapshots = await self.market.get_market_snapshots(
            item.stock_id for item in items
        )
        out: list[WatchlistItemOut] = []
        for item in items:
            snapshot = snapshots.get(item.stock_id)
            stock = snapshot.stock if snapshot else None
            prices = snapshot.prices if snapshot else ()
            indicator = snapshot.indicator if snapshot else None
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
                    rsi_14=indicator.rsi_14 if indicator else None,
                    trend=trend_signal(
                        latest.close if latest else None,
                        indicator.ema_20 if indicator else None,
                        indicator.macd_histogram if indicator else None,
                    ),
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
