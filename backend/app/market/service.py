"""Market business logic: ingestion pipeline and read/query services.

Ingestion is deterministic analytics only (no AI): fetch → validate (in the
client) → store prices → compute indicators → store. Each symbol is isolated —
one bad symbol logs and is skipped, never aborting the batch.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.market import constants as C
from app.market import indicators as ind
from app.market.exceptions import SectorNotFoundError, StockNotFoundError
from app.market.models import DailyPrice, Stock
from app.market.repository import MarketRepository
from app.market.schemas import (
    BreadthOut,
    FundamentalsOut,
    IndicatorPointOut,
    IngestionResult,
    QuoteOut,
    SectorOverviewOut,
    SectorPerformanceOut,
    StockDetailOut,
)
from app.shared.clients.market_data import MarketDataClient, PriceBar
from app.shared.clients.yfinance_client import build_default_client
from config.logging import get_logger

logger = get_logger(__name__)


def compute_indicator_points(bars: list[PriceBar]) -> list[dict]:
    """Pure: turn a sorted list of bars into per-date indicator rows.

    Only dates with at least one defined indicator are emitted (skips warm-up).
    """
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    dates = [b.date for b in bars]

    rsi = ind.rsi(closes, C.RSI_PERIOD)
    ema20 = ind.ema(closes, C.EMA_SHORT_PERIOD)
    ema50 = ind.ema(closes, C.EMA_LONG_PERIOD)
    macd_line, macd_signal, macd_hist = ind.macd(
        closes, C.MACD_FAST, C.MACD_SLOW, C.MACD_SIGNAL
    )
    bb_upper, bb_middle, bb_lower = ind.bollinger_bands(closes, C.BB_PERIOD, C.BB_NUM_STD)
    atr = ind.atr(highs, lows, closes, C.ATR_PERIOD)

    points: list[dict] = []
    for i, d in enumerate(dates):
        values = {
            "rsi_14": rsi[i],
            "ema_20": ema20[i],
            "ema_50": ema50[i],
            "macd": macd_line[i],
            "macd_signal": macd_signal[i],
            "macd_histogram": macd_hist[i],
            "bb_upper": bb_upper[i],
            "bb_middle": bb_middle[i],
            "bb_lower": bb_lower[i],
            "atr_14": atr[i],
        }
        if any(v is not None for v in values.values()):
            points.append({"date": d, **values})
    return points


class MarketIngestionService:
    def __init__(self, db: AsyncSession, client: MarketDataClient | None = None) -> None:
        self.db = db
        self.repo = MarketRepository(db)
        self.client = client or build_default_client()

    async def ingest(self, symbols: list[str] | None = None) -> IngestionResult:
        universe = symbols or list(C.DEFAULT_UNIVERSE)
        succeeded: list[str] = []
        failed: list[str] = []

        for symbol in universe:
            try:
                await self._ingest_one(symbol)
                await self.db.commit()
                succeeded.append(symbol)
                logger.info("ingest_symbol_ok", extra={"symbol": symbol})
            except Exception as exc:  # noqa: BLE001 — isolate one symbol's failure
                await self.db.rollback()
                failed.append(symbol)
                logger.error(
                    "ingest_symbol_failed",
                    extra={"symbol": symbol, "error": type(exc).__name__, "detail": str(exc)},
                )

        logger.info(
            "ingest_complete",
            extra={"requested": len(universe), "ok": len(succeeded), "failed": len(failed)},
        )
        return IngestionResult(
            requested=len(universe), succeeded=succeeded, failed=failed
        )

    async def _ingest_one(self, symbol: str) -> None:
        # yfinance is blocking — run off the event loop.
        bars = await asyncio.to_thread(self.client.fetch_daily_prices, symbol)
        fundamentals = await asyncio.to_thread(self.client.fetch_fundamentals, symbol)

        stock = await self.repo.upsert_stock(
            symbol,
            name=fundamentals.name,
            sector=fundamentals.sector,
            industry=fundamentals.industry,
            exchange=C.DEFAULT_EXCHANGE,
        )
        await self.repo.upsert_daily_prices(stock.id, bars)
        await self.repo.upsert_fundamentals(stock.id, fundamentals)
        await self.repo.upsert_indicators(stock.id, compute_indicator_points(bars))


def _quote_from_prices(stock: Stock, last_two: list[DailyPrice]) -> QuoteOut:
    latest = last_two[0] if last_two else None
    previous = last_two[1] if len(last_two) > 1 else None
    change = change_pct = None
    if latest is not None and previous is not None and previous.close:
        change = latest.close - previous.close
        change_pct = change / previous.close * 100.0
    return QuoteOut(
        symbol=stock.symbol,
        name=stock.name,
        sector=stock.sector,
        date=latest.date if latest else None,
        close=latest.close if latest else None,
        previous_close=previous.close if previous else None,
        change=change,
        change_percent=change_pct,
        volume=latest.volume if latest else None,
    )


class MarketQueryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = MarketRepository(db)

    async def _quote(self, stock: Stock) -> QuoteOut:
        last_two = await self.repo.get_last_two_prices(stock.id)
        return _quote_from_prices(stock, last_two)

    async def _all_quotes(self) -> list[QuoteOut]:
        stocks = await self.repo.list_active_stocks()
        return [await self._quote(s) for s in stocks]

    async def get_stock_detail(self, symbol: str) -> StockDetailOut:
        stock = await self.repo.get_stock_by_symbol(symbol)
        if stock is None:
            raise StockNotFoundError(symbol)
        quote = await self._quote(stock)
        fundamentals = (
            FundamentalsOut.model_validate(stock.fundamentals)
            if stock.fundamentals is not None
            else None
        )
        return StockDetailOut(
            **quote.model_dump(),
            industry=stock.industry,
            exchange=stock.exchange,
            fundamentals=fundamentals,
        )

    async def get_indicator_history(
        self, symbol: str, limit: int = 60
    ) -> list[IndicatorPointOut]:
        stock = await self.repo.get_stock_by_symbol(symbol)
        if stock is None:
            raise StockNotFoundError(symbol)
        rows = await self.repo.get_indicator_history(stock.id, limit)
        return [IndicatorPointOut.model_validate(r) for r in rows]

    async def get_sector_performance(self, sector: str) -> SectorPerformanceOut:
        stocks = await self.repo.list_stocks_by_sector(sector)
        if not stocks:
            raise SectorNotFoundError(sector)
        quotes = [await self._quote(s) for s in stocks]
        changes = [q.change_percent for q in quotes if q.change_percent is not None]
        avg = sum(changes) / len(changes) if changes else None
        return SectorPerformanceOut(
            sector=sector,
            stock_count=len(stocks),
            average_change_percent=avg,
            stocks=quotes,
        )

    async def get_sectors_overview(self) -> list[SectorOverviewOut]:
        """Per-sector average daily change across the tracked universe.

        Powers the dashboard/market sector heatmap in one query. A sector's
        count includes every stock in it; the average is over those with a
        computable day change. Sorted best-performing first.
        """
        quotes = await self._all_quotes()
        counts: dict[str, int] = {}
        changes: dict[str, list[float]] = {}
        for q in quotes:
            if not q.sector:
                continue
            counts[q.sector] = counts.get(q.sector, 0) + 1
            if q.change_percent is not None:
                changes.setdefault(q.sector, []).append(q.change_percent)
        overview = [
            SectorOverviewOut(
                sector=sector,
                stock_count=count,
                average_change_percent=(
                    sum(changes[sector]) / len(changes[sector])
                    if changes.get(sector)
                    else None
                ),
            )
            for sector, count in counts.items()
        ]
        overview.sort(
            key=lambda s: (
                s.average_change_percent is not None,
                s.average_change_percent or 0.0,
            ),
            reverse=True,
        )
        return overview

    async def get_gainers(self, limit: int = 5) -> list[QuoteOut]:
        quotes = [q for q in await self._all_quotes() if q.change_percent is not None]
        quotes.sort(key=lambda q: q.change_percent, reverse=True)
        return quotes[:limit]

    async def get_losers(self, limit: int = 5) -> list[QuoteOut]:
        quotes = [q for q in await self._all_quotes() if q.change_percent is not None]
        quotes.sort(key=lambda q: q.change_percent)
        return quotes[:limit]

    async def get_breadth(self) -> BreadthOut:
        quotes = [q for q in await self._all_quotes() if q.change_percent is not None]
        advancers = sum(1 for q in quotes if q.change_percent > 0)
        decliners = sum(1 for q in quotes if q.change_percent < 0)
        unchanged = sum(1 for q in quotes if q.change_percent == 0)
        ratio = advancers / decliners if decliners else None
        return BreadthOut(
            advancers=advancers,
            decliners=decliners,
            unchanged=unchanged,
            total=len(quotes),
            advance_decline_ratio=ratio,
        )
