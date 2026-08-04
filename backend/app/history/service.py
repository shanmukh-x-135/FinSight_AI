"""Historical intelligence service: build the index, run similarity queries.

Pipeline (all deterministic — no AI):
  market data → daily feature vectors → fit normalizer → FAISS index → statistics.

The normalizer is fitted once and persisted; both the build path and the query
path load and apply the *same* normalizer, so there is no drift between the
vectors put into the index and the vector used to query it.
"""

from __future__ import annotations

import os
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.history.constants import (
    MIN_SESSIONS_TO_BUILD,
    index_path,
    normalizer_path,
)
from app.history.embeddings import FaissIndexStore
from app.history.exceptions import (
    IndexNotBuiltError,
    InsufficientHistoryError,
    SessionNotFoundError,
)
from app.history.feature_engineering import (
    MacroDay,
    Normalizer,
    StockDay,
    compute_session_feature,
    vector_from_features,
)
from app.history.models import HistoricalSession
from app.history.repository import HistoryRepository
from app.history.schemas import (
    RebuildResult,
    SessionSummary,
    SimilarityResponse,
    SimilarSessionOut,
    StatisticsOut,
)
from app.history.similarity import (
    compute_statistics,
    distance_to_similarity,
    outcome_label,
)
from app.market.constants import MACRO_FEATURE_SYMBOLS
from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)


class HistoryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = HistoryRepository(db)

    # ----- Build -----------------------------------------------------------
    async def build_index(self) -> RebuildResult:
        session_features = await self._engineer_features()
        if len(session_features) < MIN_SESSIONS_TO_BUILD:
            raise InsufficientHistoryError(len(session_features), MIN_SESSIONS_TO_BUILD)

        # Persist sessions with their next-day outcome (label = next day's return).
        upserted: list[HistoricalSession] = []
        for i, (session_date, feat) in enumerate(session_features):
            ndr = (
                session_features[i + 1][1]["avg_return"]
                if i + 1 < len(session_features)
                else None
            )
            upserted.append(
                await self.repo.upsert_session(
                    session_date, features=feat, next_day_return=ndr,
                    outcome=outcome_label(ndr),
                )
            )

        # Fit normalizer + build FAISS index (persisted to disk).
        vectors = [vector_from_features(feat) for _d, feat in session_features]
        normalizer = Normalizer.fit(vectors)
        normalizer.save(normalizer_path())
        normalized = normalizer.transform_many(vectors)
        ids = [s.id for s in upserted]
        store = FaissIndexStore.build(ids, normalized)
        store.save(index_path())

        # Refresh embedding references.
        await self.repo.clear_embeddings()
        for s in upserted:
            await self.repo.add_embedding(s.id, faiss_id=s.id, dim=store.dim)

        # Cache the latest session's outlook statistics.
        latest = upserted[-1]
        by_id = {s.id: s for s in upserted}
        neighbours = self._search(store, normalizer, latest, settings.history_top_k)
        stats = compute_statistics(
            [by_id[i].next_day_return for i, _ in neighbours if i in by_id],
            settings.history_top_k,
        )
        await self.repo.upsert_statistics(latest.id, stats)

        await self.db.commit()
        logger.info(
            "history_index_built",
            extra={"sessions": len(ids), "dim": store.dim},
        )
        return RebuildResult(sessions_indexed=len(ids), dim=store.dim, latest_date=latest.date)

    async def _engineer_features(self) -> list[tuple[date, dict[str, float]]]:
        """Assemble each date's complete market feature vector from Phase 2 data."""
        price_rows = await self.repo.get_price_rows()  # (stock_id, date, close), sorted
        indicator_rows = await self.repo.get_indicator_rows()
        sentiment_rows = await self.repo.get_sentiment_rows()
        macro_rows = await self.repo.get_macro_price_rows(
            list(MACRO_FEATURE_SYMBOLS.values())
        )
        sentiment_by: dict[tuple[int, date], float] = {
            (sid, d): value for sid, d, value in sentiment_rows
        }

        macro_returns: dict[date, dict[str, float]] = {}
        feature_by_symbol = {
            symbol: feature for feature, symbol in MACRO_FEATURE_SYMBOLS.items()
        }
        previous_macro: dict[str, float] = {}
        for symbol, d, close in macro_rows:
            previous = previous_macro.get(symbol)
            if previous is not None and previous > 0 and close > 0:
                macro_returns.setdefault(d, {})[feature_by_symbol[symbol]] = (
                    close / previous - 1.0
                )
            previous_macro[symbol] = close

        close_by: dict[tuple[int, date], float] = {}
        prev_by: dict[tuple[int, date], float | None] = {}
        last_stock: int | None = None
        prev: float | None = None
        for stock_id, d, close in price_rows:
            if stock_id != last_stock:
                last_stock, prev = stock_id, None
            close_by[(stock_id, d)] = close
            prev_by[(stock_id, d)] = prev
            prev = close

        ind_by: dict[tuple[int, date], tuple] = {
            (row[0], row[1]): row for row in indicator_rows
        }

        stock_ids = {sid for sid, _d in close_by}
        dates = sorted({d for _sid, d in close_by})

        sessions: list[tuple[date, dict[str, float]]] = []
        for d in dates:
            stock_days: list[StockDay] = []
            for sid in stock_ids:
                if (sid, d) not in close_by:
                    continue
                ind = ind_by.get((sid, d))
                stock_days.append(
                    StockDay(
                        close=close_by[(sid, d)],
                        prev_close=prev_by[(sid, d)],
                        rsi=ind[2] if ind else None,
                        ema20=ind[3] if ind else None,
                        ema50=ind[4] if ind else None,
                        bb_upper=ind[5] if ind else None,
                        bb_lower=ind[6] if ind else None,
                        atr=ind[7] if ind else None,
                        macd_hist=ind[8] if ind else None,
                        sentiment=sentiment_by.get((sid, d)),
                    )
                )
            macro_values = macro_returns.get(d, {})
            macro = (
                MacroDay(**macro_values)
                if len(macro_values) == len(MACRO_FEATURE_SYMBOLS)
                else None
            )
            feat = compute_session_feature(stock_days, macro=macro)
            if feat is not None:
                sessions.append((d, feat))
        return sessions

    # ----- Query -----------------------------------------------------------
    async def query_similar(
        self, query_date: date | None = None, k: int | None = None
    ) -> SimilarityResponse:
        k = k or settings.history_top_k
        if not (os.path.exists(index_path()) and os.path.exists(normalizer_path())):
            raise IndexNotBuiltError()

        try:
            normalizer = Normalizer.load(normalizer_path())
            store = FaissIndexStore.load(index_path())
        except (OSError, RuntimeError, ValueError) as exc:
            logger.warning(
                "history_index_incompatible",
                extra={"error": type(exc).__name__, "detail": str(exc)},
            )
            raise IndexNotBuiltError() from exc

        session = (
            await self.repo.get_session_by_date(query_date)
            if query_date is not None
            else await self.repo.get_latest_session()
        )
        if session is None:
            raise SessionNotFoundError()

        neighbours = self._search(store, normalizer, session, k)
        by_id = await self.repo.get_sessions_by_ids([i for i, _ in neighbours])

        similar: list[SimilarSessionOut] = []
        next_day_returns: list[float | None] = []
        for nid, dist in neighbours:
            ns = by_id.get(nid)
            if ns is None:
                continue
            next_day_returns.append(ns.next_day_return)
            similar.append(
                SimilarSessionOut(
                    date=ns.date,
                    avg_return=ns.avg_return,
                    pct_advancers=ns.pct_advancers,
                    advance_decline_ratio=ns.advance_decline_ratio,
                    avg_rsi=ns.avg_rsi,
                    similarity_score=distance_to_similarity(dist),
                    distance=dist,
                    next_day_return=ns.next_day_return,
                    outcome=ns.outcome,
                )
            )

        stats = compute_statistics(next_day_returns, k)
        return SimilarityResponse(
            query_date=session.date,
            query_summary=SessionSummary(
                date=session.date,
                avg_return=session.avg_return,
                pct_advancers=session.pct_advancers,
                advance_decline_ratio=session.advance_decline_ratio,
                avg_rsi=session.avg_rsi,
            ),
            similar_sessions=similar,
            statistics=StatisticsOut(**stats),
        )

    # ----- Shared search (identical for build-stats and query) ------------
    @staticmethod
    def _search(
        store: FaissIndexStore,
        normalizer: Normalizer,
        session: HistoricalSession,
        k: int,
    ) -> list[tuple[int, float]]:
        query_vec = normalizer.transform(vector_from_features(session.feature_vector))
        # Fetch k+1 then drop the session itself (its own nearest match).
        raw = store.search(query_vec, k + 1)
        return [(i, d) for i, d in raw if i != session.id][:k]
