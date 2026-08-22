"""Failure-mode coverage for PostgreSQL-backed FAISS reconstruction."""

from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.history.artifacts import CorpusRow, HistoryArtifactCache, IndexCorpus
from app.history.constants import (
    INDEX_FILENAME,
    MANIFEST_FILENAME,
    NORMALIZER_FILENAME,
    generations_dir,
)
from app.history.exceptions import IndexNotBuiltError
from app.history.feature_engineering import FEATURE_NAMES, FEATURE_VERSION
from app.history.models import HistoricalIndexState
from app.history.service import HistoryService
from tests.history.conftest import A_DATES


def _features(offset: float = 0.0) -> dict[str, float]:
    return {name: offset + index / 100 for index, name in enumerate(FEATURE_NAMES)}


async def _state(db_session: AsyncSession) -> HistoricalIndexState:
    return (
        await db_session.execute(
            select(HistoricalIndexState).where(HistoricalIndexState.id == 1)
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_build_commits_generation_identity_and_cache(
    db_session: AsyncSession, seeded_market: None, tmp_data_dir: str
) -> None:
    await HistoryService(db_session).build_index()
    state = await _state(db_session)
    generation = Path(generations_dir()) / state.corpus_hash

    assert state.session_count == 60
    assert state.dimension == len(FEATURE_NAMES)
    assert state.feature_version == FEATURE_VERSION
    assert (generation / MANIFEST_FILENAME).is_file()
    assert (generation / INDEX_FILENAME).is_file()


@pytest.mark.asyncio
async def test_missing_cache_is_reconstructed_from_database(
    db_session: AsyncSession, seeded_market: None, tmp_data_dir: str
) -> None:
    service = HistoryService(db_session)
    await service.build_index()
    state = await _state(db_session)
    generation = Path(generations_dir()) / state.corpus_hash
    shutil.rmtree(generation)

    result = await service.query_similar(query_date=A_DATES[30], k=5)

    assert len(result.similar_sessions) == 5
    assert (generation / MANIFEST_FILENAME).is_file()


@pytest.mark.asyncio
@pytest.mark.parametrize("artifact", [MANIFEST_FILENAME, INDEX_FILENAME])
async def test_corrupt_cache_is_repaired_from_database(
    db_session: AsyncSession,
    seeded_market: None,
    tmp_data_dir: str,
    artifact: str,
) -> None:
    service = HistoryService(db_session)
    await service.build_index()
    state = await _state(db_session)
    generation = Path(generations_dir()) / state.corpus_hash
    (generation / artifact).write_bytes(b"corrupt")

    result = await service.query_similar(query_date=A_DATES[30], k=3)

    assert len(result.similar_sessions) == 3
    manifest = json.loads((generation / MANIFEST_FILENAME).read_text())
    assert manifest["corpus_hash"] == state.corpus_hash


@pytest.mark.asyncio
async def test_checksum_rejects_structurally_valid_but_modified_artifact(
    db_session: AsyncSession, seeded_market: None, tmp_data_dir: str
) -> None:
    service = HistoryService(db_session)
    await service.build_index()
    state = await _state(db_session)
    generation = Path(generations_dir()) / state.corpus_hash
    normalizer_path = generation / NORMALIZER_FILENAME
    normalizer = json.loads(normalizer_path.read_text())
    normalizer["center"][0] += 1000
    normalizer_path.write_text(json.dumps(normalizer))

    result = await service.query_similar(query_date=A_DATES[30], k=3)

    assert all(item.date in A_DATES for item in result.similar_sessions)


@pytest.mark.asyncio
async def test_cache_write_failure_does_not_break_database_backed_query(
    db_session: AsyncSession,
    seeded_market: None,
    tmp_data_dir: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = HistoryService(db_session)
    await service.build_index()
    state = await _state(db_session)
    shutil.rmtree(Path(generations_dir()) / state.corpus_hash)

    def fail_publish(*_args: object) -> None:
        raise OSError("simulated cache failure")

    monkeypatch.setattr(HistoryArtifactCache, "publish", fail_publish)
    result = await service.query_similar(query_date=A_DATES[30], k=2)
    assert len(result.similar_sessions) == 2


@pytest.mark.asyncio
async def test_build_succeeds_after_database_commit_when_cache_publish_fails(
    db_session: AsyncSession,
    seeded_market: None,
    tmp_data_dir: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_publish(*_args: object) -> None:
        raise OSError("simulated cache failure")

    monkeypatch.setattr(HistoryArtifactCache, "publish", fail_publish)
    result = await HistoryService(db_session).build_index()
    state = await _state(db_session)

    assert result.sessions_indexed == 60
    assert state.session_count == 60
    assert not (Path(generations_dir()) / state.corpus_hash).exists()


@pytest.mark.asyncio
async def test_uncommitted_build_never_publishes_generation(
    db_session: AsyncSession,
    seeded_market: None,
    tmp_data_dir: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_commit() -> None:
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="simulated database failure"):
        await HistoryService(db_session).build_index()
    assert not Path(generations_dir()).exists()


@pytest.mark.asyncio
async def test_faiss_construction_failure_leaves_no_committed_partial_corpus(
    db_session: AsyncSession,
    seeded_market: None,
    tmp_data_dir: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_reconstruct(_self: IndexCorpus) -> None:
        raise RuntimeError("simulated FAISS construction failure")

    monkeypatch.setattr(IndexCorpus, "reconstruct", fail_reconstruct)
    with pytest.raises(RuntimeError, match="FAISS construction failure"):
        await HistoryService(db_session).build_index()
    await db_session.rollback()

    assert await db_session.scalar(select(func.count(HistoricalIndexState.id))) == 0


@pytest.mark.asyncio
async def test_inconsistent_committed_state_is_not_silently_used(
    db_session: AsyncSession, seeded_market: None, tmp_data_dir: str
) -> None:
    service = HistoryService(db_session)
    await service.build_index()
    state = await _state(db_session)
    state.corpus_hash = "0" * 64
    await db_session.commit()

    with pytest.raises(IndexNotBuiltError):
        await service.query_similar()


def test_corpus_hash_is_order_independent_and_content_addressed() -> None:
    feature = _features()
    dimension = len(FEATURE_NAMES)
    first = CorpusRow(1, 1, dimension, FEATURE_VERSION, feature)
    second = CorpusRow(2, 2, dimension, FEATURE_VERSION, feature)
    forward = IndexCorpus.from_rows([first, second])
    reverse = IndexCorpus.from_rows([second, first])
    changed = IndexCorpus.from_rows(
        [
            first,
            CorpusRow(
                2,
                2,
                dimension,
                FEATURE_VERSION,
                {**feature, "equal_weight_return": 0.2},
            ),
        ]
    )

    assert forward.corpus_hash == reverse.corpus_hash
    assert forward.corpus_hash != changed.corpus_hash


def test_legacy_feature_version_is_rejected() -> None:
    with pytest.raises(ValueError, match="feature version"):
        IndexCorpus.from_rows(
            [CorpusRow(7, 7, len(FEATURE_NAMES), "legacy_v0", _features())]
        )


def test_concurrent_publishers_leave_one_valid_generation(tmp_path, monkeypatch) -> None:
    from config.settings import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    feature = _features()
    dimension = len(FEATURE_NAMES)
    corpus = IndexCorpus.from_rows(
        [
            CorpusRow(
                index,
                index,
                dimension,
                FEATURE_VERSION,
                {**feature, "equal_weight_return": index / 100},
            )
            for index in range(1, 6)
        ]
    )
    cache = HistoryArtifactCache(corpus)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _item: cache.publish(), range(8)))

    loaded_normalizer, loaded_store = cache.load()
    assert loaded_normalizer.mean.size == dimension
    assert loaded_store.ids == corpus.ids
