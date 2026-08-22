"""Integration tests for the historical intelligence service.

Seeds a controlled two-regime market (a calm-up regime in January, a
volatile-down regime in February) so similarity retrieval is verifiable:
querying a January session must return January neighbours. Also checks
determinism (rebuild → identical rankings) and the error paths.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.history.constants import index_path, normalizer_path
from app.history.embeddings import FaissIndexStore
from app.history.exceptions import IndexNotBuiltError, InsufficientHistoryError
from app.history.feature_engineering import (
    FEATURE_NAMES,
    FEATURE_VERSION,
    NORMALIZATION_METHOD,
)
from app.history.service import HistoryService
from tests.history.conftest import A_DATES, B_DATES


@pytest.mark.asyncio
async def test_build_creates_sessions_and_index(
    db_session: AsyncSession, seeded_market: None, tmp_data_dir: str
) -> None:
    result = await HistoryService(db_session).build_index()
    # Each regime needs 20 past sessions for momentum/volume/volatility features.
    assert result.sessions_indexed == 60
    assert result.candidate_sessions == 80
    assert result.rejected_sessions == 20
    assert result.dim == len(FEATURE_NAMES)
    assert result.feature_version == FEATURE_VERSION
    assert result.normalization_method == NORMALIZATION_METHOD
    assert result.latest_date == B_DATES[-1]


@pytest.mark.asyncio
async def test_similar_query_retrieves_same_regime(
    db_session: AsyncSession, seeded_market: None, tmp_data_dir: str
) -> None:
    service = HistoryService(db_session)
    await service.build_index()

    query_date = A_DATES[30]
    result = await service.query_similar(query_date=query_date, k=5)
    assert result.query_date == query_date
    assert len(result.similar_sessions) == 5
    # Every neighbour belongs to the controlled calm-up regime.
    assert all(s.date in A_DATES for s in result.similar_sessions)
    # Self is excluded.
    assert all(s.date != query_date for s in result.similar_sessions)
    # Similarity scores are sorted descending (nearest first).
    scores = [s.similarity_score for s in result.similar_sessions]
    assert scores == sorted(scores, reverse=True)
    # Statistics were computed from real neighbour outcomes.
    assert result.statistics.sample_size >= 1


@pytest.mark.asyncio
async def test_query_latest_when_no_date(
    db_session: AsyncSession, seeded_market: None, tmp_data_dir: str
) -> None:
    service = HistoryService(db_session)
    await service.build_index()
    result = await service.query_similar()
    assert result.query_date == B_DATES[-1]


@pytest.mark.asyncio
async def test_rebuild_is_reproducible(
    db_session: AsyncSession, seeded_market: None, tmp_data_dir: str
) -> None:
    service = HistoryService(db_session)

    await service.build_index()
    first = await service.query_similar(query_date=A_DATES[30], k=5)

    await service.build_index()  # rebuild from identical data
    second = await service.query_similar(query_date=A_DATES[30], k=5)

    assert [(s.date, round(s.distance, 6)) for s in first.similar_sessions] == [
        (s.date, round(s.distance, 6)) for s in second.similar_sessions
    ]


@pytest.mark.asyncio
async def test_query_before_build_raises(
    db_session: AsyncSession, seeded_market: None, tmp_data_dir: str
) -> None:
    with pytest.raises(IndexNotBuiltError):
        await HistoryService(db_session).query_similar()


@pytest.mark.asyncio
async def test_query_rejects_stale_feature_artifacts(
    db_session: AsyncSession, tmp_data_dir: str
) -> None:
    Path(normalizer_path()).parent.mkdir(parents=True)
    Path(normalizer_path()).write_text(
        json.dumps({"feature_names": ["old"], "mean": [0.0], "std": [1.0]})
    )
    FaissIndexStore.build([1], np.zeros((1, 1), dtype="float32")).save(index_path())

    with pytest.raises(IndexNotBuiltError):
        await HistoryService(db_session).query_similar()


@pytest.mark.asyncio
async def test_build_with_no_data_raises(
    db_session: AsyncSession, tmp_data_dir: str
) -> None:
    with pytest.raises(InsufficientHistoryError):
        await HistoryService(db_session).build_index()
