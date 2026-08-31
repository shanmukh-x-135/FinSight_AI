"""Data-access for the historical-intelligence domain.

Reads Phase 2 market data and persists historical sessions, index membership,
committed corpus identity, and statistics. Local FAISS files are derived cache.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import delete, exists, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.history.models import (
    HistoricalEmbedding,
    HistoricalIndexState,
    HistoricalSession,
    HistoricalStatistics,
)
from app.history.session_builder import (
    EquityIndicatorRow,
    EquityPriceRow,
    MembershipPeriod,
    UniverseStock,
)
from app.market.models import DailyPrice, IndexMembership, Indicator, Stock
from app.shared.upsert import conflict_insert


class HistoryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ----- Market data (inputs to feature engineering) --------------------
    async def get_universe_stocks(self, index_code: str) -> list[UniverseStock]:
        has_membership = exists().where(
            IndexMembership.stock_id == Stock.id,
            IndexMembership.index_code == index_code,
        )
        result = await self.db.execute(
            select(Stock.id, Stock.sector)
            .where(or_(Stock.history_eligible.is_(True), has_membership))
            .order_by(Stock.id)
        )
        return [UniverseStock(row[0], row[1]) for row in result.all()]

    async def get_memberships(self, index_code: str) -> list[MembershipPeriod]:
        result = await self.db.execute(
            select(
                IndexMembership.stock_id,
                IndexMembership.valid_from,
                IndexMembership.valid_to,
            )
            .where(IndexMembership.index_code == index_code)
            .order_by(IndexMembership.valid_from, IndexMembership.stock_id)
        )
        return [MembershipPeriod(row[0], row[1], row[2]) for row in result.all()]

    async def get_price_rows(self, stock_ids: list[int]) -> list[EquityPriceRow]:
        if not stock_ids:
            return []
        result = await self.db.execute(
            select(
                DailyPrice.stock_id,
                DailyPrice.date,
                DailyPrice.close,
                DailyPrice.volume,
            )
            .where(DailyPrice.stock_id.in_(stock_ids))
            .order_by(DailyPrice.stock_id, DailyPrice.date)
        )
        return [EquityPriceRow(row[0], row[1], row[2], row[3]) for row in result.all()]

    async def get_indicator_rows(self, stock_ids: list[int]) -> list[EquityIndicatorRow]:
        if not stock_ids:
            return []
        result = await self.db.execute(
            select(
                Indicator.stock_id,
                Indicator.date,
                Indicator.rsi_14,
                Indicator.ema_20,
                Indicator.ema_50,
                Indicator.atr_14,
            ).where(Indicator.stock_id.in_(stock_ids))
        )
        return [
            EquityIndicatorRow(
                stock_id=row[0],
                date=row[1],
                rsi=row[2],
                ema20=row[3],
                ema50=row[4],
                atr=row[5],
            )
            for row in result.all()
        ]

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
        feature_version: str,
        feature_dimension: int,
        usable_constituent_count: int,
        expected_constituent_count: int,
        coverage_ratio: float,
        sector_coverage_ratio: float,
        membership_mode: str,
        quality_flags: list[str],
        next_day_return: float | None,
        outcome: str | None,
        next_session_breadth: float | None,
        forward_5_session_return: float | None,
        forward_5_session_drawdown: float | None,
        forward_5_session_upside: float | None,
    ) -> HistoricalSession:
        values = {
            "date": session_date,
            "feature_version": feature_version,
            "feature_dimension": feature_dimension,
            "avg_return": features["equal_weight_return"],
            "median_return": features["median_return"],
            "pct_advancers": features["advancing_share"],
            "advance_decline_ratio": features["advance_decline_ratio"],
            # Backward-compatible summary column; v1 defines this as median RSI.
            "avg_rsi": features["median_rsi"],
            "feature_vector": features,
            "usable_constituent_count": usable_constituent_count,
            "expected_constituent_count": expected_constituent_count,
            "coverage_ratio": coverage_ratio,
            "sector_coverage_ratio": sector_coverage_ratio,
            "membership_mode": membership_mode,
            "quality_flags": quality_flags,
            "next_day_return": next_day_return,
            "outcome": outcome,
            "next_session_breadth": next_session_breadth,
            "forward_5_session_return": forward_5_session_return,
            "forward_5_session_drawdown": forward_5_session_drawdown,
            "forward_5_session_upside": forward_5_session_upside,
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

    async def delete_incompatible_sessions(
        self, feature_version: str, valid_dates: list[date]
    ) -> None:
        statement = delete(HistoricalSession).where(
            or_(
                HistoricalSession.feature_version != feature_version,
                HistoricalSession.date.not_in(valid_dates),
            )
        )
        await self.db.execute(statement)

    async def list_sessions(self, feature_version: str) -> list[HistoricalSession]:
        result = await self.db.execute(
            select(HistoricalSession)
            .where(HistoricalSession.feature_version == feature_version)
            .order_by(HistoricalSession.date.asc())
        )
        return list(result.scalars().all())

    async def get_session_by_date(
        self, session_date: date, feature_version: str
    ) -> HistoricalSession | None:
        result = await self.db.execute(
            select(HistoricalSession).where(
                HistoricalSession.date == session_date,
                HistoricalSession.feature_version == feature_version,
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_session(self, feature_version: str) -> HistoricalSession | None:
        result = await self.db.execute(
            select(HistoricalSession)
            .where(HistoricalSession.feature_version == feature_version)
            .order_by(HistoricalSession.date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_statistics(
        self,
    ) -> tuple[HistoricalStatistics, date] | None:
        """Latest persisted analogue outcome summary, if the corpus has one."""
        result = await self.db.execute(
            select(HistoricalStatistics, HistoricalSession.date)
            .join(
                HistoricalSession,
                HistoricalSession.id == HistoricalStatistics.session_id,
            )
            .order_by(HistoricalSession.date.desc())
            .limit(1)
        )
        row = result.one_or_none()
        return (row[0], row[1]) if row else None

    async def get_sessions_by_ids(self, ids: list[int]) -> dict[int, HistoricalSession]:
        if not ids:
            return {}
        result = await self.db.execute(
            select(HistoricalSession).where(HistoricalSession.id.in_(ids))
        )
        return {s.id: s for s in result.scalars().all()}

    async def count_sessions(self, feature_version: str) -> int:
        return len(await self.list_sessions(feature_version))

    # ----- Embeddings (index references) ----------------------------------
    async def clear_embeddings(self) -> None:
        await self.db.execute(delete(HistoricalEmbedding))
        await self.db.flush()

    async def add_embedding(
        self,
        session_id: int,
        faiss_id: int,
        dim: int,
        feature_version: str,
    ) -> None:
        stmt = conflict_insert(self.db, HistoricalEmbedding).values(
            session_id=session_id,
            faiss_id=faiss_id,
            dim=dim,
            feature_version=feature_version,
        )
        await self.db.execute(
            stmt.on_conflict_do_update(
                index_elements=[HistoricalEmbedding.session_id],
                set_={
                    "faiss_id": stmt.excluded.faiss_id,
                    "dim": stmt.excluded.dim,
                    "feature_version": stmt.excluded.feature_version,
                },
            )
        )

    async def upsert_index_state(
        self,
        *,
        corpus_hash: str,
        session_count: int,
        dimension: int,
        artifact_schema_version: int,
        feature_version: str,
        normalization_method: str,
        built_at: datetime,
    ) -> None:
        values = {
            "id": 1,
            "corpus_hash": corpus_hash,
            "session_count": session_count,
            "dimension": dimension,
            "artifact_schema_version": artifact_schema_version,
            "feature_version": feature_version,
            "normalization_method": normalization_method,
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
            .where(
                HistoricalIndexState.id == 1,
                HistoricalEmbedding.feature_version
                == HistoricalIndexState.feature_version,
                HistoricalSession.feature_version == HistoricalIndexState.feature_version,
            )
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
