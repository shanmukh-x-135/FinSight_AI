"""Market business logic: ingestion pipeline and read/query services.

Ingestion is deterministic analytics only (no AI): fetch → validate (in the
client) → store prices → compute indicators → store. Each symbol is isolated —
one bad symbol logs and is skipped, never aborting the batch.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.market import constants as C
from app.market import indicators as ind
from app.market.exceptions import SectorNotFoundError, StockNotFoundError
from app.market.models import DailyPrice, Stock
from app.market.repository import MarketRepository, PriceIngestionState
from app.market.schemas import (
    BreadthOut,
    EconomicCalendarOut,
    EconomicEventOut,
    FundamentalsOut,
    IndicatorPointOut,
    IngestionResult,
    MarketStockSnapshotOut,
    PricePointOut,
    QuoteOut,
    SectorOverviewOut,
    SectorPerformanceOut,
    StockDetailOut,
    TechnicalSummaryOut,
)
from app.market.signals import trend_signal
from app.market.universe import (
    MINIMUM_EQUITY_HISTORY_BARS,
    MINIMUM_MACRO_HISTORY_BARS,
    validate_symbol_history,
)
from app.shared.clients.economic_calendar import EconomicCalendarClient
from app.shared.clients.market_data import (
    FundamentalsData,
    MarketDataClient,
    MarketDataError,
    PriceBar,
)
from app.shared.clients.yfinance_client import build_default_client
from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)


class IngestionMode(StrEnum):
    BOOTSTRAP = "bootstrap"
    RECONCILIATION = "reconciliation"
    INCREMENTAL = "incremental"


@dataclass(frozen=True)
class PriceFetchWindow:
    start_date: date
    end_date: date
    target_trading_date: date
    mode: IngestionMode

    @property
    def is_full(self) -> bool:
        return self.mode in {IngestionMode.BOOTSTRAP, IngestionMode.RECONCILIATION}


@dataclass(frozen=True)
class SymbolIngestionOutcome:
    bars_fetched: int
    mode: IngestionMode


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(tz=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def plan_price_fetch(
    state: PriceIngestionState | None,
    target_trading_date: date,
    *,
    now: datetime | None = None,
) -> PriceFetchWindow:
    """Choose a bounded bootstrap, reconciliation, or incremental window."""
    synchronized_at = _as_utc(now)
    if state is None or state.latest_price_date is None:
        mode = IngestionMode.BOOTSTRAP
    elif state.last_full_price_sync_at is None:
        mode = IngestionMode.RECONCILIATION
    else:
        last_full = _as_utc(state.last_full_price_sync_at)
        due_at = last_full + timedelta(days=settings.market_full_reconciliation_days)
        mode = (
            IngestionMode.RECONCILIATION
            if synchronized_at >= due_at
            else IngestionMode.INCREMENTAL
        )

    if mode in {IngestionMode.BOOTSTRAP, IngestionMode.RECONCILIATION}:
        start_date = target_trading_date - timedelta(
            days=settings.market_bootstrap_lookback_days
        )
    else:
        assert state is not None and state.latest_price_date is not None
        anchor = min(state.latest_price_date, target_trading_date)
        start_date = anchor - timedelta(
            days=settings.market_incremental_overlap_days
        )
    return PriceFetchWindow(
        start_date=start_date,
        end_date=target_trading_date + timedelta(days=1),
        target_trading_date=target_trading_date,
        mode=mode,
    )


def _can_advance_full_watermark(
    state: PriceIngestionState | None, target_trading_date: date
) -> bool:
    return (
        state is None
        or state.latest_price_date is None
        or target_trading_date >= state.latest_price_date
    )


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

    async def ingest(
        self,
        symbols: list[str] | None = None,
        *,
        target_trading_date: date | None = None,
        now: datetime | None = None,
    ) -> IngestionResult:
        synchronized_at = _as_utc(now)
        target = target_trading_date or synchronized_at.astimezone(
            ZoneInfo(settings.market_timezone)
        ).date()
        universe = (
            list(symbols)
            if symbols is not None
            else [*C.DEFAULT_UNIVERSE, *C.MACRO_PROXIES]
        )
        succeeded: list[str] = []
        failed: list[str] = []
        bars_fetched = 0
        mode_counts = {mode: 0 for mode in IngestionMode}

        for symbol in universe:
            try:
                if symbol in C.MACRO_PROXIES:
                    outcome = await self._ingest_macro_one(
                        symbol, target, synchronized_at
                    )
                else:
                    outcome = await self._ingest_one(symbol, target, synchronized_at)
                await self.db.commit()
                succeeded.append(symbol)
                bars_fetched += outcome.bars_fetched
                mode_counts[outcome.mode] += 1
                logger.info(
                    "ingest_symbol_ok",
                    extra={
                        "symbol": symbol,
                        "target_trading_date": target.isoformat(),
                        "ingestion_mode": outcome.mode.value,
                        "price_bars_fetched": outcome.bars_fetched,
                    },
                )
            except Exception as exc:  # noqa: BLE001 — isolate one symbol's failure
                await self.db.rollback()
                failed.append(symbol)
                logger.error(
                    "ingest_symbol_failed",
                    extra={"symbol": symbol, "error": type(exc).__name__},
                )

        logger.info(
            "ingest_complete",
            extra={
                "requested": len(universe),
                "ok": len(succeeded),
                "failed": len(failed),
                "target_trading_date": target.isoformat(),
                "price_bars_fetched": bars_fetched,
                "bootstrap_symbols": mode_counts[IngestionMode.BOOTSTRAP],
                "reconciliation_symbols": mode_counts[IngestionMode.RECONCILIATION],
                "incremental_symbols": mode_counts[IngestionMode.INCREMENTAL],
            },
        )
        return IngestionResult(
            requested=len(universe),
            succeeded=succeeded,
            failed=failed,
            price_bars_fetched=bars_fetched,
            bootstrap_symbols=mode_counts[IngestionMode.BOOTSTRAP],
            reconciliation_symbols=mode_counts[IngestionMode.RECONCILIATION],
            incremental_symbols=mode_counts[IngestionMode.INCREMENTAL],
        )

    async def _fetch_prices(
        self, symbol: str, window: PriceFetchWindow
    ) -> list[PriceBar]:
        # Providers are blocking, so run them off-loop and enforce an external
        # deadline even when their own SDK does not expose one consistently.
        bars = await asyncio.wait_for(
            asyncio.to_thread(
                self.client.fetch_daily_prices,
                symbol,
                start_date=window.start_date,
                end_date=window.end_date,
            ),
            timeout=settings.market_fetch_timeout_seconds,
        )
        bounded = {
            bar.date: bar
            for bar in bars
            if window.start_date <= bar.date < window.end_date
        }
        if not bounded:
            raise MarketDataError(f"No valid price bars returned for {symbol}")
        validated = [bounded[day] for day in sorted(bounded)]
        validate_symbol_history(
            symbol,
            validated,
            target_date=window.target_trading_date,
            minimum_bars=(
                MINIMUM_MACRO_HISTORY_BARS
                if symbol in C.MACRO_PROXIES
                else MINIMUM_EQUITY_HISTORY_BARS
            )
            if window.is_full
            else 1,
        )
        return validated

    async def _fetch_fundamentals(self, symbol: str) -> FundamentalsData:
        return await asyncio.wait_for(
            asyncio.to_thread(self.client.fetch_fundamentals, symbol),
            timeout=settings.market_fetch_timeout_seconds,
        )

    async def _ingest_one(
        self, symbol: str, target: date, synchronized_at: datetime
    ) -> SymbolIngestionOutcome:
        state = await self.repo.get_price_ingestion_state(symbol)
        window = plan_price_fetch(state, target, now=synchronized_at)
        bars = await self._fetch_prices(symbol, window)
        fundamentals = (
            await self._fetch_fundamentals(symbol)
            if window.is_full
            else None
        )

        stock = await self.repo.upsert_stock(
            symbol,
            name=fundamentals.name if fundamentals is not None else None,
            sector=fundamentals.sector if fundamentals is not None else None,
            industry=fundamentals.industry if fundamentals is not None else None,
            exchange=C.DEFAULT_EXCHANGE,
            is_active=True,
        )
        await self.repo.upsert_daily_prices(stock.id, bars)
        if fundamentals is not None:
            await self.repo.upsert_fundamentals(stock.id, fundamentals)
        canonical_bars = [
            PriceBar(row.date, row.open, row.high, row.low, row.close, row.volume)
            for row in await self.repo.get_price_history(stock.id)
        ]
        affected_points = [
            point
            for point in compute_indicator_points(canonical_bars)
            if point["date"] >= window.start_date
        ]
        await self.repo.upsert_indicators(stock.id, affected_points)
        if window.is_full and _can_advance_full_watermark(state, target):
            await self.repo.mark_full_price_sync(stock.id, synchronized_at)
        for retired, replacement in C.RETIRED_SYMBOL_REPLACEMENTS.items():
            if replacement == symbol:
                await self.repo.deactivate_stock(retired)
        return SymbolIngestionOutcome(len(bars), window.mode)

    async def _ingest_macro_one(
        self, symbol: str, target: date, synchronized_at: datetime
    ) -> SymbolIngestionOutcome:
        """Persist one cross-asset proxy without exposing it as an equity."""
        state = await self.repo.get_price_ingestion_state(symbol)
        window = plan_price_fetch(state, target, now=synchronized_at)
        bars = await self._fetch_prices(symbol, window)
        name, asset_class = C.MACRO_PROXIES[symbol]
        stock = await self.repo.upsert_stock(
            symbol,
            name=name,
            sector="Macro",
            industry=asset_class,
            exchange="GLOBAL",
            is_active=False,
        )
        await self.repo.upsert_daily_prices(stock.id, bars)
        if window.is_full and _can_advance_full_watermark(state, target):
            await self.repo.mark_full_price_sync(stock.id, synchronized_at)
        return SymbolIngestionOutcome(len(bars), window.mode)


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
        snapshots = await self.repo.get_market_snapshots(
            (stock.id for stock in stocks), known_stocks=stocks
        )
        return [
            _quote_from_prices(stock, list(snapshots[stock.id].prices))
            for stock in stocks
            if stock.id in snapshots
        ]

    @staticmethod
    def _gainers_from(quotes: list[QuoteOut], limit: int) -> list[QuoteOut]:
        changed = [q for q in quotes if q.change_percent is not None]
        changed.sort(key=lambda q: q.change_percent, reverse=True)
        return changed[:limit]

    @staticmethod
    def _losers_from(quotes: list[QuoteOut], limit: int) -> list[QuoteOut]:
        changed = [q for q in quotes if q.change_percent is not None]
        changed.sort(key=lambda q: q.change_percent)
        return changed[:limit]

    @staticmethod
    def _breadth_from(quotes: list[QuoteOut]) -> BreadthOut:
        changed = [q for q in quotes if q.change_percent is not None]
        advancers = sum(1 for q in changed if q.change_percent > 0)
        decliners = sum(1 for q in changed if q.change_percent < 0)
        unchanged = sum(1 for q in changed if q.change_percent == 0)
        return BreadthOut(
            advancers=advancers,
            decliners=decliners,
            unchanged=unchanged,
            total=len(changed),
            advance_decline_ratio=advancers / decliners if decliners else None,
        )

    async def get_market_overview(
        self, limit: int = 5
    ) -> tuple[BreadthOut, list[QuoteOut], list[QuoteOut]]:
        """Build breadth and movers from one batched universe read."""
        quotes = await self._all_quotes()
        return (
            self._breadth_from(quotes),
            self._gainers_from(quotes, limit),
            self._losers_from(quotes, limit),
        )

    async def list_market_stocks(self) -> list[MarketStockSnapshotOut]:
        """Dense, batched universe rows for the market research table."""
        stocks = await self.repo.list_active_stocks()
        snapshots = await self.repo.get_market_snapshots(
            (stock.id for stock in stocks), known_stocks=stocks
        )
        rows: list[MarketStockSnapshotOut] = []
        for stock in stocks:
            snapshot = snapshots.get(stock.id)
            if snapshot is None:
                continue
            quote = _quote_from_prices(stock, list(snapshot.prices))
            indicator = snapshot.indicator
            rows.append(
                MarketStockSnapshotOut(
                    **quote.model_dump(),
                    rsi_14=indicator.rsi_14 if indicator else None,
                    ema_20=indicator.ema_20 if indicator else None,
                    ema_50=indicator.ema_50 if indicator else None,
                    macd_histogram=indicator.macd_histogram if indicator else None,
                    trend=trend_signal(
                        quote.close,
                        indicator.ema_20 if indicator else None,
                        indicator.macd_histogram if indicator else None,
                    ),
                )
            )
        rows.sort(key=lambda row: row.symbol)
        return rows

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

    async def get_price_history(
        self, symbol: str, limit: int = 260
    ) -> list[PricePointOut]:
        stock = await self.repo.get_stock_by_symbol(symbol)
        if stock is None:
            raise StockNotFoundError(symbol)
        rows = await self.repo.get_price_history(stock.id, limit)
        return [PricePointOut.model_validate(row) for row in rows]

    async def get_sector_performance(self, sector: str) -> SectorPerformanceOut:
        stocks = await self.repo.list_stocks_by_sector(sector)
        if not stocks:
            raise SectorNotFoundError(sector)
        snapshots = await self.repo.get_market_snapshots(
            (stock.id for stock in stocks), known_stocks=stocks
        )
        quotes = [
            _quote_from_prices(stock, list(snapshots[stock.id].prices))
            for stock in stocks
            if stock.id in snapshots
        ]
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
        return self._gainers_from(await self._all_quotes(), limit)

    async def get_losers(self, limit: int = 5) -> list[QuoteOut]:
        return self._losers_from(await self._all_quotes(), limit)

    async def get_breadth(self) -> BreadthOut:
        return self._breadth_from(await self._all_quotes())

    async def get_technical_summary(self) -> TechnicalSummaryOut:
        rows = await self.repo.list_latest_indicators_with_close()
        indicators = [row for row, _close in rows]
        rsi_values = [row.rsi_14 for row in indicators if row.rsi_14 is not None]
        atr_values = [
            row.atr_14 / close * 100
            for row, close in rows
            if row.atr_14 is not None and close
        ]
        return TechnicalSummaryOut(
            as_of=max((row.date for row in indicators), default=None),
            stocks_with_indicators=len(rows),
            average_rsi=sum(rsi_values) / len(rsi_values) if rsi_values else None,
            bullish_rsi_count=sum(value >= 55 for value in rsi_values),
            overbought_count=sum(value >= 70 for value in rsi_values),
            oversold_count=sum(value <= 35 for value in rsi_values),
            above_ema20_count=sum(
                close > row.ema_20
                for row, close in rows
                if close is not None and row.ema_20 is not None
            ),
            above_ema50_count=sum(
                close > row.ema_50
                for row, close in rows
                if close is not None and row.ema_50 is not None
            ),
            positive_macd_count=sum(
                row.macd_histogram > 0
                for row in indicators
                if row.macd_histogram is not None
            ),
            average_atr_percent=(
                sum(atr_values) / len(atr_values) if atr_values else None
            ),
        )


class EconomicCalendarService:
    def __init__(self, client: EconomicCalendarClient | None) -> None:
        self.client = client

    async def upcoming(self, start_date: date, end_date: date) -> EconomicCalendarOut:
        if self.client is None:
            return EconomicCalendarOut(status="not_configured", events=[])
        try:
            events = await self.client.fetch_events(start_date, end_date)
        except Exception as exc:  # noqa: BLE001 — provider failures degrade explicitly
            logger.warning(
                "economic_calendar_unavailable",
                extra={"error": type(exc).__name__},
            )
            return EconomicCalendarOut(status="unavailable", events=[])
        return EconomicCalendarOut(
            status="ok",
            events=[EconomicEventOut(**event.__dict__) for event in events],
        )
