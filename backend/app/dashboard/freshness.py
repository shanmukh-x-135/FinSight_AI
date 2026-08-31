"""Deterministic freshness states for user-visible research datasets."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dashboard.schemas import DataFreshnessOut
from app.history.models import HistoricalSession
from app.market.models import UniverseSnapshot
from app.market.repository import MarketRepository
from app.news.models import NewsArticle
from app.scheduler.readiness import NSETradingCalendar
from app.shared.time import as_utc, utc_now


def _state(observed: date | None, expected: date) -> str:
    if observed is None:
        return "Unavailable"
    return "Fresh" if observed >= expected else "Delayed"


def latest_ready_trading_date(now: datetime, calendar: NSETradingCalendar) -> date:
    for offset in range(10):
        candidate = now.date() - timedelta(days=offset)
        session = calendar.session(candidate)
        if session is not None and now >= session.data_ready_at:
            return candidate
    return now.date()


class FreshnessService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, *, now: datetime | None = None) -> list[DataFreshnessOut]:
        current = as_utc(now) if now is not None else utc_now()
        expected = latest_ready_trading_date(current, NSETradingCalendar())
        market_date = await MarketRepository(self.db).get_latest_active_price_date()
        news_value = await self.db.scalar(select(func.max(NewsArticle.fetched_at)))
        news_at = as_utc(news_value) if news_value is not None else None
        universe_value = await self.db.scalar(
            select(func.max(UniverseSnapshot.fetched_at))
        )
        universe_at = as_utc(universe_value) if universe_value is not None else None
        history_row = (
            await self.db.execute(
                select(HistoricalSession.date, HistoricalSession.created_at)
                .order_by(HistoricalSession.date.desc())
                .limit(1)
            )
        ).one_or_none()

        news_state = (
            "Unavailable"
            if news_at is None
            else "Fresh"
            if current - news_at <= timedelta(hours=36)
            else "Delayed"
        )
        universe_state = (
            "Unavailable"
            if universe_at is None
            else "Fresh"
            if current - universe_at <= timedelta(days=8)
            else "Delayed"
        )
        history_date = history_row[0] if history_row else None
        history_at = as_utc(history_row[1]) if history_row else None
        return [
            DataFreshnessOut(
                dataset="market",
                state=_state(market_date, expected),
                observed_date=market_date,
                observed_at=None,
                expected_trading_date=expected,
                explanation=(
                    "Latest price session is provider-ready."
                    if market_date is not None and market_date >= expected
                    else "Latest provider-ready market session is not available."
                ),
            ),
            DataFreshnessOut(
                dataset="news",
                state=news_state,
                observed_date=news_at.date() if news_at else None,
                observed_at=news_at,
                expected_trading_date=expected,
                explanation=(
                    "News ingestion completed within 36 hours."
                    if news_state == "Fresh"
                    else "Recent news ingestion is delayed or unavailable."
                ),
            ),
            DataFreshnessOut(
                dataset="universe",
                state=universe_state,
                observed_date=universe_at.date() if universe_at else None,
                observed_at=universe_at,
                expected_trading_date=None,
                explanation=(
                    "Universe snapshot was refreshed within 8 days."
                    if universe_state == "Fresh"
                    else "Universe snapshot is delayed or unavailable."
                ),
            ),
            DataFreshnessOut(
                dataset="historical_corpus",
                state=_state(history_date, expected),
                observed_date=history_date,
                observed_at=history_at,
                expected_trading_date=expected,
                explanation=(
                    "Historical corpus includes the latest provider-ready session."
                    if history_date is not None and history_date >= expected
                    else "Historical corpus is delayed or unavailable."
                ),
            ),
        ]
