"""Market business logic: ingestion pipeline and read/query services.

Ingestion is deterministic analytics only (no AI): fetch → validate (in the
client) → store prices → compute indicators → store. Each symbol is isolated —
one bad symbol logs and is skipped, never aborting the batch.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.history.repository import HistoryRepository
from app.market import constants as C
from app.market import indicators as ind
from app.market.attribution import conflict_summary, directional_view, technical_view
from app.market.exceptions import (
    SectorNotFoundError,
    StockNotFoundError,
    UniverseNotInitializedError,
)
from app.market.models import DailyPrice, Stock
from app.market.repository import (
    MarketRepository,
    MarketSnapshot,
    PriceIngestionState,
    ReturnWindows,
)
from app.market.schemas import (
    AttributionDriverOut,
    BreadthOut,
    ConflictSignalOut,
    EconomicCalendarOut,
    EconomicEventOut,
    FundamentalsOut,
    HeatmapStockOut,
    IndicatorPointOut,
    IngestionResult,
    MarketStockSnapshotOut,
    MarketWorkspaceOut,
    MovementAttributionOut,
    PricePointOut,
    QuoteOut,
    SectorOverviewOut,
    SectorPerformanceOut,
    SectorRotationOut,
    StockDetailOut,
    TechnicalSummaryOut,
    UniverseOptionOut,
)
from app.market.signals import trend_signal
from app.market.universe import (
    MINIMUM_EQUITY_HISTORY_BARS,
    MINIMUM_MACRO_HISTORY_BARS,
    validate_symbol_history,
)
from app.market.universe_provider import INDEX_DEFINITIONS
from app.news.schemas import LatestSentimentOut
from app.news.service import NewsService
from app.shared.clients.economic_calendar import EconomicCalendarClient
from app.shared.clients.market_data import (
    FundamentalsData,
    MarketDataClient,
    MarketDataError,
    PriceBar,
)
from app.shared.clients.yfinance_client import build_default_client
from app.shared.time import as_utc, utc_now
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


def plan_price_fetch(
    state: PriceIngestionState | None,
    target_trading_date: date,
    *,
    now: datetime | None = None,
) -> PriceFetchWindow:
    """Choose a bounded bootstrap, reconciliation, or incremental window."""
    synchronized_at = as_utc(now) if now is not None else utc_now()
    if state is None or state.latest_price_date is None:
        mode = IngestionMode.BOOTSTRAP
    elif state.last_full_price_sync_at is None:
        mode = IngestionMode.RECONCILIATION
    else:
        last_full = as_utc(state.last_full_price_sync_at)
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
        start_date = anchor - timedelta(days=settings.market_incremental_overlap_days)
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
        synchronized_at = as_utc(now) if now is not None else utc_now()
        target = (
            target_trading_date
            or synchronized_at.astimezone(ZoneInfo(settings.market_timezone)).date()
        )
        if symbols is not None:
            universe = list(dict.fromkeys(symbols))
        else:
            approved = await self.repo.list_approved_equities(settings.research_universe)
            if not approved:
                raise UniverseNotInitializedError()
            universe = [
                *(stock.symbol for stock in approved),
                *C.MACRO_PROXIES,
            ]
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
        fundamentals = await self._fetch_fundamentals(symbol) if window.is_full else None

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


def sector_rotation_regime(
    return_1d: float | None,
    return_5d: float | None,
    return_20d: float | None,
) -> str:
    """Classify sector momentum from comparable per-session return rates."""
    if return_1d is None or return_5d is None or return_20d is None:
        return "unavailable"
    one_rate, five_rate, twenty_rate = return_1d, return_5d / 5, return_20d / 20
    if one_rate > five_rate > twenty_rate:
        return "improving"
    if one_rate < five_rate < twenty_rate:
        return "weakening"
    if one_rate > 0 and five_rate > 0 and twenty_rate > 0:
        return "leader"
    if one_rate < 0 and five_rate < 0 and twenty_rate < 0:
        return "laggard"
    return "mixed"


class MarketQueryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = MarketRepository(db)

    async def _quote(self, stock: Stock) -> QuoteOut:
        last_two = await self.repo.get_last_two_prices(stock.id)
        return _quote_from_prices(stock, last_two)

    async def _stocks(self, index_code: str | None = None) -> list[Stock]:
        return (
            await self.repo.list_approved_equities(index_code)
            if index_code is not None
            else await self.repo.list_active_stocks()
        )

    async def _all_quotes(self, index_code: str | None = None) -> list[QuoteOut]:
        stocks = await self._stocks(index_code)
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
        changed = [
            q for q in quotes if q.change_percent is not None and q.change_percent > 0
        ]
        changed.sort(key=lambda q: q.change_percent, reverse=True)
        return changed[:limit]

    @staticmethod
    def _losers_from(quotes: list[QuoteOut], limit: int) -> list[QuoteOut]:
        changed = [
            q for q in quotes if q.change_percent is not None and q.change_percent < 0
        ]
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
        self, limit: int = 5, index_code: str | None = None
    ) -> tuple[BreadthOut, list[QuoteOut], list[QuoteOut]]:
        """Build breadth and movers from one batched universe read."""
        quotes = await self._all_quotes(index_code)
        return (
            self._breadth_from(quotes),
            self._gainers_from(quotes, limit),
            self._losers_from(quotes, limit),
        )

    async def list_market_stocks(
        self, index_code: str | None = None
    ) -> list[MarketStockSnapshotOut]:
        """Dense, batched universe rows for the market research table."""
        stocks = await self._stocks(index_code)
        snapshots = await self.repo.get_market_snapshots(
            (stock.id for stock in stocks), known_stocks=stocks
        )
        return self._market_rows_from(stocks, snapshots)

    @staticmethod
    def _market_rows_from(
        stocks: list[Stock], snapshots: dict[int, MarketSnapshot]
    ) -> list[MarketStockSnapshotOut]:
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

    @staticmethod
    def _sectors_from(quotes: list[QuoteOut]) -> list[SectorOverviewOut]:
        counts: dict[str, int] = {}
        changes: dict[str, list[float]] = {}
        for quote in quotes:
            if not quote.sector:
                continue
            counts[quote.sector] = counts.get(quote.sector, 0) + 1
            if quote.change_percent is not None:
                changes.setdefault(quote.sector, []).append(quote.change_percent)
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
            key=lambda row: (
                row.average_change_percent is not None,
                row.average_change_percent or 0.0,
            ),
            reverse=True,
        )
        return overview

    @staticmethod
    def _heatmap_from(
        stocks: list[Stock],
        snapshots: dict[int, MarketSnapshot],
        sentiment_rows: list[LatestSentimentOut],
    ) -> list[HeatmapStockOut]:
        sentiment = {row.symbol: row for row in sentiment_rows}
        rows: list[HeatmapStockOut] = []
        for stock in stocks:
            snapshot = snapshots.get(stock.id)
            if snapshot is None or not stock.sector:
                continue
            quote = _quote_from_prices(stock, list(snapshot.prices))
            news = sentiment.get(stock.symbol)
            rows.append(
                HeatmapStockOut(
                    symbol=stock.symbol,
                    name=stock.name,
                    sector=stock.sector,
                    as_of=quote.date,
                    change_percent=quote.change_percent,
                    market_cap=(
                        stock.fundamentals.market_cap if stock.fundamentals else None
                    ),
                    sentiment=news.latest_sentiment if news else None,
                    sentiment_availability=(
                        news.availability if news else "no_relevant_news"
                    ),
                    rsi_14=snapshot.indicator.rsi_14 if snapshot.indicator else None,
                    signal=trend_signal(
                        quote.close,
                        snapshot.indicator.ema_20 if snapshot.indicator else None,
                        snapshot.indicator.macd_histogram if snapshot.indicator else None,
                    ),
                )
            )
        return sorted(rows, key=lambda row: (row.sector, row.symbol))

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

    async def get_movement_attribution(self, symbol: str) -> MovementAttributionOut:
        """Describe observable contributors without asserting causal certainty."""
        stock = await self.repo.get_stock_by_symbol(symbol)
        if stock is None:
            raise StockNotFoundError(symbol)

        stocks = await self.repo.list_active_stocks()
        snapshots = await self.repo.get_market_snapshots(
            (item.id for item in stocks), known_stocks=stocks
        )
        snapshot = snapshots.get(stock.id)
        quote = (
            _quote_from_prices(stock, list(snapshot.prices))
            if snapshot is not None
            else await self._quote(stock)
        )
        indicator = snapshot.indicator if snapshot is not None else None
        quotes = [
            _quote_from_prices(item, list(snapshots[item.id].prices))
            for item in stocks
            if item.id in snapshots
        ]
        market_changes = [
            item.change_percent
            for item in quotes
            if item.sector is not None and item.change_percent is not None
        ]
        sector_changes = [
            item.change_percent
            for item in quotes
            if item.sector == stock.sector and item.change_percent is not None
        ]
        market_return = (
            sum(market_changes) / len(market_changes) if market_changes else None
        )
        sector_return = (
            sum(sector_changes) / len(sector_changes) if sector_changes else None
        )

        sentiment = await NewsService(self.db).get_stock_sentiment(symbol)
        history_row = await HistoryRepository(self.db).get_latest_statistics()
        history = (
            history_row[0]
            if history_row is not None and history_row[1] == quote.date
            else None
        )
        technical_direction, technical_observation, technical_confidence = technical_view(
            quote.close,
            indicator.ema_20 if indicator else None,
            indicator.macd_histogram if indicator else None,
        )

        price_rows = await self.repo.get_price_history(stock.id, 22)
        relative_volume = None
        if len(price_rows) >= 2:
            prior_volumes = [row.volume for row in price_rows[:-1] if row.volume > 0]
            if prior_volumes:
                relative_volume = price_rows[-1].volume / (
                    sum(prior_volumes) / len(prior_volumes)
                )

        news_direction = directional_view(sentiment.latest_sentiment, band=0.1)
        news_observation = (
            f"{sentiment.article_count} verified article association(s); "
            f"aggregate sentiment {sentiment.latest_sentiment:+.2f}"
            if sentiment.latest_sentiment is not None
            else "No verified company catalyst identified in the recent news window"
        )
        historical_probability = history.bullish_probability if history else None
        historical_direction = (
            "unavailable"
            if historical_probability is None
            else (
                "bullish"
                if historical_probability > 0.55
                else "bearish"
                if historical_probability < 0.45
                else "neutral"
            )
        )
        historical_confidence = (
            min(0.85, (history.sample_size / 20) * abs(historical_probability - 0.5) * 2)
            if history and historical_probability is not None
            else 0.0
        )
        historical_observation = (
            f"{historical_probability * 100:.0f}% of {history.sample_size} comparable "
            "market sessions closed higher next session"
            if history and historical_probability is not None
            else "Historical analogue outcomes unavailable"
        )

        corporate_evidence = [
            item
            for item in sentiment.evidence
            if item.event_category == "Corporate Action"
        ]
        sector_direction = directional_view(sector_return, band=0.15)
        market_direction = directional_view(market_return, band=0.15)
        volume_direction = "unavailable" if relative_volume is None else "neutral"
        macro_context = {
            "Energy": "Energy-sector returns can be associated with crude and refining conditions",
            "Financial Services": "Financial-sector returns can be associated with rates and liquidity",
            "Technology": "Technology-sector returns can be associated with global demand and USD/INR",
        }.get(stock.sector or "")

        driver_values = [
            (
                "company_news",
                "Company-specific news",
                news_observation,
                news_direction,
                "high" if sentiment.evidence else "unavailable",
                sentiment.confidence or 0.0,
                sentiment.latest_sentiment,
                [item.id for item in sentiment.evidence],
            ),
            (
                "sector",
                f"{stock.sector or 'Sector'} return",
                f"Sector average return {sector_return:+.2f}%"
                if sector_return is not None
                else "Sector return unavailable",
                sector_direction,
                "high" if sector_return is not None else "unavailable",
                0.8 if sector_return is not None else 0.0,
                sector_return,
                [],
            ),
            (
                "market",
                "Broad-market return",
                f"Tracked-universe average return {market_return:+.2f}%"
                if market_return is not None
                else "Broad-market return unavailable",
                market_direction,
                "medium" if market_return is not None else "unavailable",
                0.7 if market_return is not None else 0.0,
                market_return,
                [],
            ),
            (
                "technical",
                "Technical momentum",
                technical_observation,
                technical_direction,
                "medium" if technical_direction != "unavailable" else "unavailable",
                technical_confidence,
                None,
                [],
            ),
            (
                "volume",
                "Volume regime",
                f"Volume was {relative_volume:.2f}× its prior-session average"
                if relative_volume is not None
                else "Volume regime unavailable",
                volume_direction,
                "medium" if relative_volume is not None else "unavailable",
                0.65 if relative_volume is not None else 0.0,
                None,
                [],
            ),
            (
                "historical",
                "Similar historical regimes",
                historical_observation,
                historical_direction,
                "medium" if history else "unavailable",
                historical_confidence,
                None,
                [],
            ),
            (
                "macro",
                "Macro exposure",
                macro_context
                or "No deterministic macro-exposure rule is available for this sector",
                "neutral" if macro_context else "unavailable",
                "low" if macro_context else "unavailable",
                0.4 if macro_context else 0.0,
                None,
                [],
            ),
            (
                "corporate_action",
                "Corporate actions",
                f"{len(corporate_evidence)} verified corporate-action article(s) identified"
                if corporate_evidence
                else "No verified corporate action identified",
                news_direction if corporate_evidence else "unavailable",
                "high" if corporate_evidence else "unavailable",
                sentiment.confidence or 0.0 if corporate_evidence else 0.0,
                None,
                [item.id for item in corporate_evidence],
            ),
        ]
        drivers = [
            AttributionDriverOut(
                rank=index,
                category=category,
                label=label,
                observation=observation,
                direction=direction,
                relevance=relevance,
                confidence=round(confidence, 4),
                value_percent=value,
                evidence_article_ids=article_ids,
            )
            for index, (
                category,
                label,
                observation,
                direction,
                relevance,
                confidence,
                value,
                article_ids,
            ) in enumerate(driver_values, start=1)
        ]
        signals = [
            ConflictSignalOut(
                source="Technical",
                direction=technical_direction,
                confidence=technical_confidence,
                observation=technical_observation,
            ),
            ConflictSignalOut(
                source="News",
                direction=news_direction,
                confidence=sentiment.confidence or 0.0,
                observation=news_observation,
            ),
            ConflictSignalOut(
                source="Sector",
                direction=sector_direction,
                confidence=0.8 if sector_return is not None else 0.0,
                observation=drivers[1].observation,
            ),
            ConflictSignalOut(
                source="Historical regime",
                direction=historical_direction,
                confidence=historical_confidence,
                observation=historical_observation,
            ),
        ]
        available_count = sum(driver.direction != "unavailable" for driver in drivers)
        return MovementAttributionOut(
            symbol=stock.symbol,
            as_of=quote.date,
            change_percent=quote.change_percent,
            summary=(
                f"{available_count} observable contributor(s) were evaluated. "
                "These are associations, not proven causes."
            ),
            drivers=drivers,
            evidence_conflict=conflict_summary(signals),
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

    async def get_sector_performance(
        self, sector: str, index_code: str | None = None
    ) -> SectorPerformanceOut:
        stocks = (
            [stock for stock in await self._stocks(index_code) if stock.sector == sector]
            if index_code is not None
            else await self.repo.list_stocks_by_sector(sector)
        )
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

    async def get_sectors_overview(
        self, index_code: str | None = None
    ) -> list[SectorOverviewOut]:
        """Per-sector average daily change across the tracked universe.

        Powers the dashboard/market sector heatmap in one query. A sector's
        count includes every stock in it; the average is over those with a
        computable day change. Sorted best-performing first.
        """
        quotes = await self._all_quotes(index_code)
        return self._sectors_from(quotes)

    async def list_universes(self) -> list[UniverseOptionOut]:
        counts = await self.repo.active_universe_counts()
        return [
            UniverseOptionOut(
                code=code,
                label=label,
                expected_constituents=expected,
                active_constituents=counts.get(code, 0),
                initialized=counts.get(code, 0) == expected,
                preferred=code == settings.research_universe,
                source_url=source_url,
            )
            for code, (label, source_url, expected) in INDEX_DEFINITIONS.items()
        ]

    async def get_heatmap(self, index_code: str) -> list[HeatmapStockOut]:
        stocks = await self._stocks(index_code)
        snapshots = await self.repo.get_market_snapshots(
            (stock.id for stock in stocks), known_stocks=stocks
        )
        sentiment_rows = await NewsService(self.db).list_latest_sentiment()
        return self._heatmap_from(stocks, snapshots, sentiment_rows)

    async def get_workspace(
        self,
        index_code: str,
        economic_events: EconomicCalendarOut,
    ) -> MarketWorkspaceOut:
        """Build the market workspace from one shared universe snapshot."""
        stocks = await self._stocks(index_code)
        snapshots = await self.repo.get_market_snapshots(
            (stock.id for stock in stocks), known_stocks=stocks
        )
        quotes = [
            _quote_from_prices(stock, list(snapshots[stock.id].prices))
            for stock in stocks
            if stock.id in snapshots
        ]
        sentiment = await NewsService(self.db).list_latest_sentiment()
        symbols = {stock.symbol for stock in stocks}
        sentiment = [row for row in sentiment if row.symbol in symbols]
        technical = await self._technical_summary_for(stocks)
        windows = await self.repo.get_return_windows(stock.id for stock in stocks)
        return MarketWorkspaceOut(
            universe=index_code,
            stocks=self._market_rows_from(stocks, snapshots),
            breadth=self._breadth_from(quotes),
            sectors=self._sectors_from(quotes),
            technical=technical,
            heatmap=self._heatmap_from(stocks, snapshots, sentiment),
            sector_rotation=self._rotation_from(stocks, windows),
            economic_events=economic_events,
            sentiment=sentiment,
        )

    async def get_sector_rotation(self, index_code: str) -> list[SectorRotationOut]:
        stocks = await self._stocks(index_code)
        windows = await self.repo.get_return_windows(stock.id for stock in stocks)
        return self._rotation_from(stocks, windows)

    @staticmethod
    def _rotation_from(
        stocks: list[Stock], windows: dict[int, ReturnWindows]
    ) -> list[SectorRotationOut]:
        by_sector: dict[str, list[ReturnWindows]] = {}
        for stock in stocks:
            if stock.sector and stock.id in windows:
                by_sector.setdefault(stock.sector, []).append(windows[stock.id])

        def average(values: list[float | None]) -> float | None:
            available = [value for value in values if value is not None]
            return sum(available) / len(available) if available else None

        rows = []
        for sector, items in by_sector.items():
            one = average([item.return_1d for item in items])
            five = average([item.return_5d for item in items])
            twenty = average([item.return_20d for item in items])
            rows.append(
                SectorRotationOut(
                    sector=sector,
                    stock_count=len(items),
                    return_1d=one,
                    return_5d=five,
                    return_20d=twenty,
                    momentum_regime=sector_rotation_regime(one, five, twenty),
                )
            )
        rows.sort(
            key=lambda row: (
                row.return_20d is not None,
                row.return_20d or float("-inf"),
            ),
            reverse=True,
        )
        return rows

    async def get_gainers(
        self, limit: int = 5, index_code: str | None = None
    ) -> list[QuoteOut]:
        return self._gainers_from(await self._all_quotes(index_code), limit)

    async def get_losers(
        self, limit: int = 5, index_code: str | None = None
    ) -> list[QuoteOut]:
        return self._losers_from(await self._all_quotes(index_code), limit)

    async def get_breadth(self, index_code: str | None = None) -> BreadthOut:
        return self._breadth_from(await self._all_quotes(index_code))

    async def get_technical_summary(
        self, index_code: str | None = None
    ) -> TechnicalSummaryOut:
        stocks = await self._stocks(index_code) if index_code is not None else None
        return await self._technical_summary_for(stocks)

    async def _technical_summary_for(
        self, stocks: list[Stock] | None
    ) -> TechnicalSummaryOut:
        rows = await self.repo.list_latest_indicators_with_close(
            (stock.id for stock in stocks) if stocks is not None else None
        )
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
