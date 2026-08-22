"""PostgreSQL restart and disk-loss coverage for P10.6."""

from __future__ import annotations

import os
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.history.artifacts import CorpusRow, IndexCorpus
from app.history.constants import ARTIFACT_SCHEMA_VERSION, generations_dir
from app.history.feature_engineering import (
    FEATURE_NAMES,
    FEATURE_VERSION,
    NORMALIZATION_METHOD,
)
from app.history.models import (
    HistoricalEmbedding,
    HistoricalIndexState,
    HistoricalSession,
)
from app.history.repository import HistoryRepository
from app.history.service import HistoryService
from config.settings import settings

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL, reason="TEST_POSTGRES_URL is required for PostgreSQL integration"
)


def _features(offset: float) -> dict[str, float]:
    return {name: offset + index / 1000 for index, name in enumerate(FEATURE_NAMES)}


@pytest.mark.asyncio
async def test_postgres_reconstructs_faiss_after_process_restart_and_disk_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert POSTGRES_URL is not None
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    engine = create_async_engine(POSTGRES_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    test_dates = [date(2098, 6, day) for day in range(1, 7)]
    old_state: dict[str, object] | None = None

    try:
        async with factory() as db:
            existing_state = await db.scalar(select(HistoricalIndexState))
            if existing_state is not None:
                old_state = {
                    "corpus_hash": existing_state.corpus_hash,
                    "session_count": existing_state.session_count,
                    "dimension": existing_state.dimension,
                    "feature_version": existing_state.feature_version,
                    "normalization_method": existing_state.normalization_method,
                    "artifact_schema_version": existing_state.artifact_schema_version,
                    "built_at": existing_state.built_at,
                }

            sessions: list[HistoricalSession] = []
            for index, session_date in enumerate(test_dates):
                feature = _features(index / 1000)
                session = HistoricalSession(
                    date=session_date,
                    feature_version=FEATURE_VERSION,
                    feature_dimension=len(FEATURE_NAMES),
                    avg_return=feature["equal_weight_return"],
                    median_return=feature["median_return"],
                    pct_advancers=feature["advancing_share"],
                    advance_decline_ratio=feature["advance_decline_ratio"],
                    avg_rsi=feature["median_rsi"],
                    feature_vector=feature,
                    usable_constituent_count=50,
                    expected_constituent_count=50,
                    coverage_ratio=1.0,
                    sector_coverage_ratio=1.0,
                    membership_mode="effective",
                    quality_flags=[],
                    next_day_return=feature["equal_weight_return"],
                    outcome="bullish",
                )
                db.add(session)
                sessions.append(session)
            await db.flush()
            db.add_all(
                HistoricalEmbedding(
                    session_id=item.id,
                    faiss_id=item.id,
                    dim=len(FEATURE_NAMES),
                    feature_version=FEATURE_VERSION,
                )
                for item in sessions
            )
            await db.flush()

            snapshot = (
                await db.execute(
                    select(HistoricalEmbedding, HistoricalSession)
                    .join(
                        HistoricalSession,
                        HistoricalSession.id == HistoricalEmbedding.session_id,
                    )
                    .order_by(HistoricalSession.id)
                )
            ).all()
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
            await HistoryRepository(db).upsert_index_state(
                corpus_hash=corpus.corpus_hash,
                session_count=len(corpus.ids),
                dimension=corpus.dimension,
                artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
                feature_version=FEATURE_VERSION,
                normalization_method=NORMALIZATION_METHOD,
                built_at=datetime.now(tz=timezone.utc),
            )
            await db.commit()

        await engine.dispose()
        shutil.rmtree(Path(generations_dir()), ignore_errors=True)

        # A fresh engine/session represents a new web process with no local cache.
        restarted_engine = create_async_engine(POSTGRES_URL)
        restarted_factory = async_sessionmaker(restarted_engine, expire_on_commit=False)
        async with restarted_factory() as db:
            result = await HistoryService(db).query_similar(test_dates[3], k=3)
            assert len(result.similar_sessions) == 3
        await restarted_engine.dispose()
        assert (Path(generations_dir()) / corpus.corpus_hash).is_dir()
    finally:
        cleanup_engine = create_async_engine(POSTGRES_URL)
        cleanup_factory = async_sessionmaker(cleanup_engine, expire_on_commit=False)
        async with cleanup_factory.begin() as db:
            await db.execute(
                delete(HistoricalSession).where(HistoricalSession.date.in_(test_dates))
            )
            if old_state is None:
                await db.execute(delete(HistoricalIndexState))
            else:
                await HistoryRepository(db).upsert_index_state(**old_state)
        await cleanup_engine.dispose()
