"""Membership-aware, point-in-time data assembly for deterministic replay."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.models import DailyPrice, IndexMembership, Indicator, Stock
from app.news.models import NewsArticle, NewsArticleStock
from app.strategy.engine import BenchmarkBar, SignalBar
from app.strategy.exceptions import BacktestDataError
from app.strategy.schemas import MembershipMode


@dataclass(frozen=True)
class BacktestData:
    bars: tuple[SignalBar, ...]
    benchmark: tuple[BenchmarkBar, ...]
    membership_disclaimer: str


@dataclass(frozen=True)
class _RawBar:
    stock_id: int
    symbol: str
    sector: str | None
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    ema_20: float | None
    ema_50: float | None
    rsi: float | None
    macd_histogram: float | None


@dataclass(frozen=True)
class _ComputedBar:
    raw: _RawBar
    return_1d: float | None
    momentum_20d: float | None
    volume_ratio: float | None


class BacktestDataLoader:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def load(
        self,
        *,
        start_date: date,
        end_date: date,
        universe_code: str,
        membership_mode: MembershipMode,
        benchmark_symbol: str,
    ) -> BacktestData:
        stocks, memberships, disclaimer = await self._universe(
            universe_code, membership_mode, start_date, end_date
        )
        if not stocks:
            raise BacktestDataError(
                f"No {universe_code} constituents are available for this range."
            )
        stock_ids = [stock.id for stock in stocks]
        warmup_start = start_date - timedelta(days=90)
        result = await self.db.execute(
            select(
                Stock.id,
                Stock.symbol,
                Stock.sector,
                DailyPrice.date,
                DailyPrice.open,
                DailyPrice.high,
                DailyPrice.low,
                DailyPrice.close,
                DailyPrice.volume,
                Indicator.ema_20,
                Indicator.ema_50,
                Indicator.rsi_14,
                Indicator.macd_histogram,
            )
            .join(DailyPrice, DailyPrice.stock_id == Stock.id)
            .outerjoin(
                Indicator,
                and_(
                    Indicator.stock_id == Stock.id,
                    Indicator.date == DailyPrice.date,
                ),
            )
            .where(
                Stock.id.in_(stock_ids),
                DailyPrice.date >= warmup_start,
                DailyPrice.date <= end_date,
            )
            .order_by(Stock.symbol, DailyPrice.date)
        )
        grouped: dict[int, list[_RawBar]] = {}
        for row in result:
            grouped.setdefault(row.id, []).append(
                _RawBar(
                    stock_id=row.id,
                    symbol=row.symbol,
                    sector=row.sector,
                    date=row.date,
                    open=row.open,
                    high=row.high,
                    low=row.low,
                    close=row.close,
                    volume=row.volume,
                    ema_20=row.ema_20,
                    ema_50=row.ema_50,
                    rsi=row.rsi_14,
                    macd_histogram=row.macd_histogram,
                )
            )

        periods: dict[int, list[tuple[date, date | None]]] = {}
        for membership in memberships:
            periods.setdefault(membership.stock_id, []).append(
                (membership.valid_from, membership.valid_to)
            )

        computed: list[_ComputedBar] = []
        for stock_id in sorted(grouped):
            closes: list[float] = []
            volumes: list[int] = []
            for row in grouped[stock_id]:
                one_day = row.close / closes[-1] - 1 if closes else None
                momentum = row.close / closes[-20] - 1 if len(closes) >= 20 else None
                prior_volumes = volumes[-20:]
                median_volume = (
                    statistics.median(prior_volumes) if len(prior_volumes) == 20 else None
                )
                volume_ratio = (
                    row.volume / median_volume
                    if median_volume is not None and median_volume > 0
                    else None
                )
                eligible = membership_mode == "current_universe" or any(
                    valid_from <= row.date and (valid_to is None or row.date < valid_to)
                    for valid_from, valid_to in periods.get(stock_id, [])
                )
                if start_date <= row.date <= end_date and eligible:
                    computed.append(_ComputedBar(row, one_day, momentum, volume_ratio))
                closes.append(row.close)
                volumes.append(row.volume)

        by_date: dict[date, list[_ComputedBar]] = {}
        for row in computed:
            by_date.setdefault(row.raw.date, []).append(row)
        news_by = await self._point_in_time_news(
            stock_ids, sorted(by_date), start_date, end_date
        )
        bars: list[SignalBar] = []
        for session_date in sorted(by_date):
            session = by_date[session_date]
            returns = [row.return_1d for row in session if row.return_1d is not None]
            breadth = (
                sum(value > 0 for value in returns) / len(returns) if returns else None
            )
            regime = (
                "broad_positive"
                if breadth is not None and breadth >= 0.60
                else "broad_negative"
                if breadth is not None and breadth <= 0.40
                else "mixed"
                if breadth is not None
                else None
            )
            sector_momentum: dict[str, float] = {}
            sectors = {row.raw.sector for row in session if row.raw.sector}
            for sector in sectors:
                values = [
                    row.momentum_20d
                    for row in session
                    if row.raw.sector == sector and row.momentum_20d is not None
                ]
                if values:
                    sector_momentum[str(sector)] = statistics.fmean(values) * 100
            for row in sorted(session, key=lambda item: item.raw.symbol):
                raw = row.raw
                bars.append(
                    SignalBar(
                        stock_id=raw.stock_id,
                        symbol=raw.symbol,
                        sector=raw.sector,
                        date=raw.date,
                        open=raw.open,
                        high=raw.high,
                        low=raw.low,
                        close=raw.close,
                        volume=raw.volume,
                        ema_20=raw.ema_20,
                        ema_50=raw.ema_50,
                        rsi=raw.rsi,
                        macd_histogram=raw.macd_histogram,
                        volume_ratio=row.volume_ratio,
                        sector_momentum_20d=(
                            sector_momentum.get(raw.sector) if raw.sector else None
                        ),
                        market_breadth=breadth,
                        market_regime=regime,
                        news_sentiment=news_by.get((raw.stock_id, raw.date)),
                    )
                )
        if not bars:
            raise BacktestDataError("No eligible priced sessions exist in this range.")
        benchmark = await self._benchmark(benchmark_symbol, start_date, end_date)
        if len(benchmark) < 2:
            raise BacktestDataError(
                f"Benchmark {benchmark_symbol} needs at least two priced sessions."
            )
        return BacktestData(tuple(bars), tuple(benchmark), disclaimer)

    async def _point_in_time_news(
        self,
        stock_ids: list[int],
        session_dates: list[date],
        start_date: date,
        end_date: date,
    ) -> dict[tuple[int, date], float]:
        """Assign articles only after they were knowable at an NSE close."""
        if not stock_ids or not session_dates:
            return {}
        lower = datetime.combine(
            start_date - timedelta(days=7), time.min, tzinfo=timezone.utc
        )
        upper = datetime.combine(
            end_date + timedelta(days=1), time.max, tzinfo=timezone.utc
        )
        known_at = func.coalesce(NewsArticle.published_at, NewsArticle.fetched_at)
        result = await self.db.execute(
            select(
                NewsArticleStock.stock_id,
                known_at,
                NewsArticle.sentiment_score,
            )
            .join(NewsArticle, NewsArticle.id == NewsArticleStock.article_id)
            .where(
                NewsArticleStock.stock_id.in_(stock_ids),
                known_at >= lower,
                known_at <= upper,
            )
            .order_by(known_at, NewsArticle.id)
        )
        market_tz = ZoneInfo("Asia/Kolkata")
        close_time = time(15, 30)
        buckets: dict[tuple[int, date], list[float]] = {}
        for stock_id, available_at, score in result:
            if available_at.tzinfo is None:
                available_at = available_at.replace(tzinfo=timezone.utc)
            local = available_at.astimezone(market_tz)
            eligible = next(
                (
                    session_date
                    for session_date in session_dates
                    if session_date > local.date()
                    or (
                        session_date == local.date()
                        and local.time().replace(tzinfo=None) <= close_time
                    )
                ),
                None,
            )
            if eligible is not None:
                buckets.setdefault((stock_id, eligible), []).append(score)
        return {
            key: statistics.fmean(values)
            for key, values in buckets.items()
            if values
        }

    async def _universe(
        self,
        index_code: str,
        membership_mode: MembershipMode,
        start_date: date,
        end_date: date,
    ) -> tuple[list[Stock], list[IndexMembership], str]:
        memberships_result = await self.db.execute(
            select(IndexMembership)
            .where(
                IndexMembership.index_code == index_code,
                IndexMembership.valid_from <= end_date,
                or_(
                    IndexMembership.valid_to.is_(None),
                    IndexMembership.valid_to > start_date,
                ),
            )
            .order_by(IndexMembership.valid_from, IndexMembership.stock_id)
        )
        memberships = list(memberships_result.scalars())
        if membership_mode == "historical_membership":
            known_from = await self.db.scalar(
                select(func.min(IndexMembership.valid_from)).where(
                    IndexMembership.index_code == index_code
                )
            )
            if known_from is None or start_date < known_from:
                raise BacktestDataError(
                    "Historical membership is not recorded for the full requested range."
                )
            ids = sorted({membership.stock_id for membership in memberships})
            disclaimer = (
                "Uses recorded effective-dated membership for every replayed session; "
                f"coverage begins {known_from.isoformat()}."
            )
        else:
            ids_result = await self.db.execute(
                select(IndexMembership.stock_id).where(
                    IndexMembership.index_code == index_code,
                    IndexMembership.valid_to.is_(None),
                )
            )
            ids = sorted(set(ids_result.scalars()))
            disclaimer = (
                "Uses today's active constituents across the full test and may contain "
                "survivorship bias. It is not historically membership-accurate."
            )
        stocks_result = await self.db.execute(
            select(Stock).where(Stock.id.in_(ids)).order_by(Stock.symbol)
        )
        return list(stocks_result.scalars()), memberships, disclaimer

    async def _benchmark(
        self, symbol: str, start_date: date, end_date: date
    ) -> list[BenchmarkBar]:
        result = await self.db.execute(
            select(DailyPrice.date, DailyPrice.close)
            .join(Stock, Stock.id == DailyPrice.stock_id)
            .where(
                Stock.symbol == symbol,
                DailyPrice.date >= start_date,
                DailyPrice.date <= end_date,
            )
            .order_by(DailyPrice.date)
        )
        return [BenchmarkBar(day, close) for day, close in result.all()]
