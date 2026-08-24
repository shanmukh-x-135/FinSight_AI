"""Versioned market-regime reconstruction, FAISS build, and similarity query."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone
from time import monotonic

from sqlalchemy.ext.asyncio import AsyncSession

from app.history.artifacts import CorpusRow, HistoryArtifactCache, IndexCorpus
from app.history.constants import ARTIFACT_SCHEMA_VERSION, MIN_SESSIONS_TO_BUILD
from app.history.embeddings import FaissIndexStore
from app.history.exceptions import (
    IndexNotBuiltError,
    InsufficientHistoryError,
    SessionNotFoundError,
)
from app.history.feature_engineering import (
    FEATURE_NAMES,
    FEATURE_VERSION,
    NORMALIZATION_METHOD,
    Normalizer,
    vector_from_features,
)
from app.history.models import HistoricalSession
from app.history.repository import HistoryRepository
from app.history.schemas import (
    FactorComparison,
    RebuildResult,
    SessionSummary,
    SimilarityResponse,
    SimilarSessionOut,
    StatisticsOut,
)
from app.history.session_builder import (
    EngineeredSession,
    ReconstructionResult,
    RegimeSessionBuilder,
)
from app.history.similarity import (
    compare_feature_groups,
    compute_statistics,
    distance_to_similarity,
    normalized_l2_distance,
    outcome_label,
)
from app.market.constants import MACRO_FEATURE_SYMBOLS
from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)
INDEX_CODE = "NIFTY50"


class HistoryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = HistoryRepository(db)

    async def build_index(self) -> RebuildResult:
        started = monotonic()
        reconstruction = await self._engineer_features()
        engineered = list(reconstruction.sessions)
        if len(engineered) < MIN_SESSIONS_TO_BUILD:
            raise InsufficientHistoryError(len(engineered), MIN_SESSIONS_TO_BUILD)

        upserted: list[HistoricalSession] = []
        for index, item in enumerate(engineered):
            features = item.quality.features
            assert features is not None
            forward = self._forward_outcome(engineered, index)
            next_return = forward[0]
            upserted.append(
                await self.repo.upsert_session(
                    item.date,
                    features=features,
                    feature_version=FEATURE_VERSION,
                    feature_dimension=len(FEATURE_NAMES),
                    usable_constituent_count=item.quality.usable_constituent_count,
                    expected_constituent_count=item.quality.expected_constituent_count,
                    coverage_ratio=item.quality.coverage_ratio,
                    sector_coverage_ratio=item.quality.sector_coverage_ratio,
                    membership_mode=item.quality.membership_mode.value,
                    quality_flags=list(item.quality.quality_flags),
                    next_day_return=next_return,
                    outcome=outcome_label(next_return),
                    next_session_breadth=forward[1],
                    forward_5_session_return=forward[2],
                    forward_5_session_drawdown=forward[3],
                    forward_5_session_upside=forward[4],
                )
            )

        await self.repo.delete_incompatible_sessions(
            FEATURE_VERSION, [item.date for item in engineered]
        )
        corpus = IndexCorpus.from_rows(
            CorpusRow(
                session_id=session.id,
                faiss_id=session.id,
                dimension=session.feature_dimension,
                feature_version=session.feature_version,
                feature_vector=session.feature_vector,
            )
            for session in upserted
        )
        normalizer, store = corpus.reconstruct()

        await self.repo.clear_embeddings()
        for session in upserted:
            await self.repo.add_embedding(
                session.id,
                faiss_id=session.id,
                dim=store.dim,
                feature_version=FEATURE_VERSION,
            )

        built_at = datetime.now(tz=timezone.utc)
        await self.repo.upsert_index_state(
            corpus_hash=corpus.corpus_hash,
            session_count=len(corpus.ids),
            dimension=corpus.dimension,
            artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
            feature_version=FEATURE_VERSION,
            normalization_method=NORMALIZATION_METHOD,
            built_at=built_at,
        )

        latest = upserted[-1]
        by_id = {session.id: session for session in upserted}
        neighbours = self._search(store, normalizer, latest, settings.history_top_k)
        stats = compute_statistics(
            [by_id[session_id].next_day_return for session_id, _ in neighbours],
            settings.history_top_k,
        )
        await self.repo.upsert_statistics(latest.id, stats)

        await self.db.commit()
        try:
            await asyncio.to_thread(HistoryArtifactCache(corpus).publish)
        except (OSError, RuntimeError, ValueError) as exc:
            logger.warning(
                "history_artifact_publish_failed",
                extra={"error": type(exc).__name__, "generation": corpus.corpus_hash},
            )
        duration = monotonic() - started
        approximate_bytes = len(corpus.ids) * (corpus.dimension * 4 + 8)
        logger.info(
            "history_index_built",
            extra={
                "feature_version": FEATURE_VERSION,
                "sessions": len(corpus.ids),
                "candidate_sessions": reconstruction.candidate_sessions,
                "rejected_sessions": reconstruction.rejected_sessions,
                "rejection_reasons": reconstruction.rejection_reasons,
                "dimension": store.dim,
                "duration_seconds": round(duration, 3),
                "approximate_index_bytes": approximate_bytes,
            },
        )
        return RebuildResult(
            sessions_indexed=len(corpus.ids),
            dim=store.dim,
            latest_date=latest.date,
            feature_version=FEATURE_VERSION,
            normalization_method=NORMALIZATION_METHOD,
            candidate_sessions=reconstruction.candidate_sessions,
            rejected_sessions=reconstruction.rejected_sessions,
            rejection_reasons=reconstruction.rejection_reasons,
            build_duration_seconds=duration,
            approximate_index_bytes=approximate_bytes,
        )

    async def _engineer_features(self) -> ReconstructionResult:
        stocks = await self.repo.get_universe_stocks(INDEX_CODE)
        stock_ids = [stock.stock_id for stock in stocks]
        return RegimeSessionBuilder().build(
            stocks=stocks,
            memberships=await self.repo.get_memberships(INDEX_CODE),
            prices=await self.repo.get_price_rows(stock_ids),
            indicators=await self.repo.get_indicator_rows(stock_ids),
            macro_prices=await self.repo.get_macro_price_rows(
                list(MACRO_FEATURE_SYMBOLS.values())
            ),
        )

    @staticmethod
    def _forward_outcome(
        sessions: list[EngineeredSession], index: int
    ) -> tuple[float | None, float | None, float | None, float | None, float | None]:
        next_item = sessions[index + 1] if index + 1 < len(sessions) else None
        if (
            next_item is None
            or next_item.candidate_index != sessions[index].candidate_index + 1
        ):
            return None, None, None, None, None
        next_features = next_item.quality.features if next_item else None
        next_return = next_features["equal_weight_return"] if next_features else None
        next_breadth = next_features["advancing_share"] if next_features else None
        horizon = sessions[index + 1 : index + 6]
        expected_indices = range(
            sessions[index].candidate_index + 1,
            sessions[index].candidate_index + 6,
        )
        if len(horizon) < 5 or any(
            item.candidate_index != expected
            for item, expected in zip(horizon, expected_indices, strict=True)
        ):
            return next_return, next_breadth, None, None, None
        wealth = 1.0
        peak = 1.0
        max_drawdown = 0.0
        max_upside = 0.0
        for item in horizon:
            features = item.quality.features
            assert features is not None
            wealth *= 1.0 + features["equal_weight_return"]
            peak = max(peak, wealth)
            max_drawdown = min(max_drawdown, wealth / peak - 1.0)
            max_upside = max(max_upside, wealth - 1.0)
        return next_return, next_breadth, wealth - 1.0, max_drawdown, max_upside

    async def query_similar(
        self, query_date: date | None = None, k: int | None = None
    ) -> SimilarityResponse:
        k = k or settings.history_top_k
        state, snapshot = await self.repo.get_index_snapshot()
        if state is None:
            raise IndexNotBuiltError()
        try:
            corpus = IndexCorpus.from_rows(
                CorpusRow(
                    session_id=session.id,
                    faiss_id=embedding.faiss_id,
                    dimension=embedding.dim,
                    feature_version=embedding.feature_version,
                    feature_vector=session.feature_vector,
                )
                for embedding, session in snapshot
            )
            if (
                state.artifact_schema_version != ARTIFACT_SCHEMA_VERSION
                or state.feature_version != FEATURE_VERSION
                or state.normalization_method != NORMALIZATION_METHOD
                or state.corpus_hash != corpus.corpus_hash
                or state.session_count != len(corpus.ids)
                or state.dimension != corpus.dimension
            ):
                raise ValueError("Committed history index state is inconsistent")
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "history_index_incompatible", extra={"error": type(exc).__name__}
            )
            raise IndexNotBuiltError() from exc

        normalizer, store = await self._load_artifacts(corpus)
        indexed_sessions = [session for _embedding, session in snapshot]
        session = (
            max(indexed_sessions, key=lambda item: item.date, default=None)
            if query_date is None
            else next(
                (item for item in indexed_sessions if item.date == query_date), None
            )
        )
        if session is None:
            raise SessionNotFoundError()

        neighbours = self._search(store, normalizer, session, k)
        by_id = await self.repo.get_sessions_by_ids(
            [session_id for session_id, _ in neighbours]
        )
        similar: list[SimilarSessionOut] = []
        next_returns: list[float | None] = []
        for session_id, squared_distance in neighbours:
            analogue = by_id.get(session_id)
            if analogue is None:
                continue
            normalized_distance = normalized_l2_distance(
                squared_distance, corpus.dimension
            )
            matching, diverging = compare_feature_groups(
                session.feature_vector, analogue.feature_vector, normalizer
            )
            next_returns.append(analogue.next_day_return)
            similar.append(
                SimilarSessionOut(
                    **self._summary(analogue).model_dump(),
                    similarity_score=distance_to_similarity(normalized_distance),
                    distance=normalized_distance,
                    next_day_return=analogue.next_day_return,
                    outcome=analogue.outcome,
                    next_session_breadth=analogue.next_session_breadth,
                    forward_5_session_return=analogue.forward_5_session_return,
                    forward_5_session_drawdown=analogue.forward_5_session_drawdown,
                    forward_5_session_upside=analogue.forward_5_session_upside,
                    matching_factors=[FactorComparison(**item) for item in matching],
                    divergence_factors=[FactorComparison(**item) for item in diverging],
                )
            )
        return SimilarityResponse(
            feature_version=FEATURE_VERSION,
            vector_dimension=corpus.dimension,
            normalization_method=NORMALIZATION_METHOD,
            query_date=session.date,
            query_summary=self._summary(session),
            similar_sessions=similar,
            statistics=StatisticsOut(**compute_statistics(next_returns, k)),
        )

    @staticmethod
    def _summary(session: HistoricalSession) -> SessionSummary:
        features = session.feature_vector
        advancing = features["advancing_share"]
        median_rsi = features["median_rsi"]
        momentum = features["median_momentum_20"]
        volatility = max(
            features["median_atr_pct"], features["median_realized_volatility_20"]
        )
        return SessionSummary(
            date=session.date,
            avg_return=session.avg_return,
            pct_advancers=session.pct_advancers,
            advance_decline_ratio=session.advance_decline_ratio,
            avg_rsi=session.avg_rsi,
            feature_version=session.feature_version,
            median_rsi=median_rsi,
            median_atr_percent=features["median_atr_pct"] * 100.0,
            median_relative_volume=features["median_relative_volume_20"],
            coverage_ratio=session.coverage_ratio,
            usable_constituents=session.usable_constituent_count,
            expected_constituents=session.expected_constituent_count,
            membership_mode=session.membership_mode,
            quality_flags=session.quality_flags,
            breadth_regime=(
                "broad_positive"
                if advancing >= 0.60
                else "broad_negative"
                if advancing <= 0.40
                else "mixed"
            ),
            momentum_regime=(
                "positive"
                if median_rsi >= 55 and momentum > 0
                else "negative"
                if median_rsi <= 45 and momentum < 0
                else "neutral"
            ),
            volatility_regime=(
                "high"
                if volatility >= 0.025
                else "low"
                if volatility <= 0.012
                else "normal"
            ),
        )

    @staticmethod
    async def _load_artifacts(
        corpus: IndexCorpus,
    ) -> tuple[Normalizer, FaissIndexStore]:
        cache = HistoryArtifactCache(corpus)
        try:
            return await asyncio.to_thread(cache.load)
        except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            logger.info(
                "history_artifact_reconstructing",
                extra={"reason": type(exc).__name__, "generation": corpus.corpus_hash},
            )
        normalizer, store = await asyncio.to_thread(corpus.reconstruct)
        try:
            await asyncio.to_thread(cache.publish)
        except (OSError, RuntimeError, ValueError) as exc:
            logger.warning(
                "history_artifact_repair_failed",
                extra={"error": type(exc).__name__, "generation": corpus.corpus_hash},
            )
        return normalizer, store

    @staticmethod
    def _search(
        store: FaissIndexStore,
        normalizer: Normalizer,
        session: HistoricalSession,
        k: int,
    ) -> list[tuple[int, float]]:
        query = normalizer.transform(vector_from_features(session.feature_vector))
        return [
            (session_id, distance)
            for session_id, distance in store.search(query, k + 1)
            if session_id != session.id
        ][:k]
