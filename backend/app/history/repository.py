"""Data-access for the historical-intelligence domain.

Reads Phase 2 market data and persists historical sessions, index membership,
committed corpus identity, and statistics. Local FAISS files are derived cache.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import delete, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.history.models import (
    HistoricalEmbedding,
    HistoricalIndexState,
    HistoricalSession,
    HistoricalStatistics,
)
from app.market.models import DailyPrice, Indicator, Stock
from app.news.models import SentimentDaily
from app.shared.upsert import conflict_insert


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

    async def get_macro_price_rows(
        self, symbols: list[str]
    ) -> list[tuple[str, date, float]]:
        """Validated proxy closes used to derive deterministic macro returns."""
        result = await self.db.execute(
            select(Stock.symbol, DailyPrice.date, DailyPrice.close)
            .join(Stock, Stock.id == DailyPrice.stock_id)
            .where(Stock.symbol.in_(symbols), Stock.is_active.is_(False))
            .order_by(Stock.symbol, DailyPrice.date)
        )
        return [(row[0], row[1], row[2]) for row in result.all()]

    # ----- Sessions -------------------------------------------------------
    async def upsert_session(
        self,
        session_date: date,
        *,
        features: dict[str, float],
        next_day_return: float | None,
        outcome: str | None,
    ) -> HistoricalSession:
        values = {
            "date": session_date,
            "avg_return": features["avg_return"],
            "median_return": features["median_return"],
            "pct_advancers": features["pct_advancers"],
            "advance_decline_ratio": features["advance_decline_ratio"],
            "avg_rsi": features["avg_rsi"],
            "feature_vector": features,
            "next_day_return": next_day_return,
            "outcome": outcome,
        }
        stmt = conflict_insert(self.db, HistoricalSession).values(**values)
        result = await self.db.execute(
            stmt.on_conflict_do_update(
                index_elements=[HistoricalSession.date],
                set_={
                    key: getattr(stmt.excluded, key) for key in values if key != "date"
                },
            )
            .returning(HistoricalSession)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one()

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

    async def get_sessions_by_ids(self, ids: list[int]) -> dict[int, HistoricalSession]:
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
        stmt = conflict_insert(self.db, HistoricalEmbedding).values(
            session_id=session_id, faiss_id=faiss_id, dim=dim
        )
        await self.db.execute(
            stmt.on_conflict_do_update(
                index_elements=[HistoricalEmbedding.session_id],
                set_={"faiss_id": stmt.excluded.faiss_id, "dim": stmt.excluded.dim},
            )
        )

    async def upsert_index_state(
        self,
        *,
        corpus_hash: str,
        session_count: int,
        dimension: int,
        artifact_schema_version: int,
        built_at: datetime,
    ) -> None:
        values = {
            "id": 1,
            "corpus_hash": corpus_hash,
            "session_count": session_count,
            "dimension": dimension,
            "artifact_schema_version": artifact_schema_version,
            "built_at": built_at,
            "updated_at": built_at,
        }
        stmt = conflict_insert(self.db, HistoricalIndexState).values(**values)
        await self.db.execute(
            stmt.on_conflict_do_update(
                index_elements=[HistoricalIndexState.id],
                set_={key: getattr(stmt.excluded, key) for key in values if key != "id"},
            )
        )

    async def get_index_snapshot(
        self,
    ) -> tuple[
        HistoricalIndexState | None, list[tuple[HistoricalEmbedding, HistoricalSession]]
    ]:
        """Read state, membership, and raw vectors in one database statement."""
        result = await self.db.execute(
            select(HistoricalIndexState, HistoricalEmbedding, HistoricalSession)
            .select_from(HistoricalIndexState)
            .join(HistoricalEmbedding, true())
            .join(
                HistoricalSession, HistoricalSession.id == HistoricalEmbedding.session_id
            )
            .where(HistoricalIndexState.id == 1)
            .order_by(HistoricalSession.id)
        )
        rows = result.all()
        if not rows:
            return None, []
        return rows[0][0], [(row[1], row[2]) for row in rows]

    # ----- Statistics -----------------------------------------------------
    async def upsert_statistics(self, session_id: int, stats: dict) -> None:
        values = {"session_id": session_id, **stats}
        stmt = conflict_insert(self.db, HistoricalStatistics).values(**values)
        await self.db.execute(
            stmt.on_conflict_do_update(
                index_elements=[HistoricalStatistics.session_id],
                set_={key: getattr(stmt.excluded, key) for key in stats},
            )
        )
