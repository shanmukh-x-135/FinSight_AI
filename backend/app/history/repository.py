"""Data-access for the historical-intelligence domain.

Reads Phase 2 market data (prices + indicators) to build feature vectors, and
persists the three historical tables. Embedding vectors themselves live in the
on-disk FAISS index — this layer only stores the reference rows.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.history.models import (
    HistoricalEmbedding,
    HistoricalSession,
    HistoricalStatistics,
)
from app.market.models import DailyPrice, Indicator, Stock
from app.news.models import SentimentDaily


class HistoryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ----- Market data (inputs to feature engineering) --------------------
    async def get_price_rows(self) -> list[tuple[int, date, float]]:
        result = await self.db.execute(
            select(DailyPrice.stock_id, DailyPrice.date, DailyPrice.close)
            .join(Stock, Stock.id == DailyPrice.stock_id)
            .where(Stock.is_active.is_(True))
            .order_by(DailyPrice.stock_id, DailyPrice.date)
        )
        return [(r[0], r[1], r[2]) for r in result.all()]

    async def get_sentiment_rows(self) -> list[tuple[int, date, float]]:
        """(stock_id, date, avg_sentiment) from the daily sentiment aggregate."""
        result = await self.db.execute(
            select(
                SentimentDaily.stock_id, SentimentDaily.date, SentimentDaily.avg_sentiment
            )
        )
        return [(r[0], r[1], r[2]) for r in result.all()]

    async def get_indicator_rows(self) -> list[tuple]:
        result = await self.db.execute(
            select(
                Indicator.stock_id,
                Indicator.date,
                Indicator.rsi_14,
                Indicator.ema_20,
                Indicator.ema_50,
                Indicator.bb_upper,
                Indicator.bb_lower,
                Indicator.atr_14,
                Indicator.macd_histogram,
            )
            .join(Stock, Stock.id == Indicator.stock_id)
            .where(Stock.is_active.is_(True))
        )
        return list(result.all())

    # ----- Sessions -------------------------------------------------------
    async def upsert_session(
        self,
        session_date: date,
        *,
        features: dict[str, float],
        next_day_return: float | None,
        outcome: str | None,
    ) -> HistoricalSession:
        result = await self.db.execute(
            select(HistoricalSession).where(HistoricalSession.date == session_date)
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = HistoricalSession(date=session_date)
            self.db.add(row)
        row.avg_return = features["avg_return"]
        row.median_return = features["median_return"]
        row.pct_advancers = features["pct_advancers"]
        row.advance_decline_ratio = features["advance_decline_ratio"]
        row.avg_rsi = features["avg_rsi"]
        row.feature_vector = features
        row.next_day_return = next_day_return
        row.outcome = outcome
        await self.db.flush()
        return row

    async def list_sessions(self) -> list[HistoricalSession]:
        result = await self.db.execute(
            select(HistoricalSession).order_by(HistoricalSession.date.asc())
        )
        return list(result.scalars().all())

    async def get_session_by_date(self, session_date: date) -> HistoricalSession | None:
        result = await self.db.execute(
            select(HistoricalSession).where(HistoricalSession.date == session_date)
        )
        return result.scalar_one_or_none()

    async def get_latest_session(self) -> HistoricalSession | None:
        result = await self.db.execute(
            select(HistoricalSession).order_by(HistoricalSession.date.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_sessions_by_ids(
        self, ids: list[int]
    ) -> dict[int, HistoricalSession]:
        if not ids:
            return {}
        result = await self.db.execute(
            select(HistoricalSession).where(HistoricalSession.id.in_(ids))
        )
        return {s.id: s for s in result.scalars().all()}

    async def count_sessions(self) -> int:
        return len(await self.list_sessions())

    # ----- Embeddings (index references) ----------------------------------
    async def clear_embeddings(self) -> None:
        await self.db.execute(delete(HistoricalEmbedding))
        await self.db.flush()

    async def add_embedding(self, session_id: int, faiss_id: int, dim: int) -> None:
        self.db.add(
            HistoricalEmbedding(session_id=session_id, faiss_id=faiss_id, dim=dim)
        )
        await self.db.flush()

    # ----- Statistics -----------------------------------------------------
    async def upsert_statistics(self, session_id: int, stats: dict) -> None:
        result = await self.db.execute(
            select(HistoricalStatistics).where(
                HistoricalStatistics.session_id == session_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = HistoricalStatistics(session_id=session_id)
            self.db.add(row)
        for key, value in stats.items():
            setattr(row, key, value)
        await self.db.flush()
