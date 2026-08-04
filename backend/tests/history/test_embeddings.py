"""Tests for the FAISS index store: retrieval correctness, persistence,
determinism."""

from __future__ import annotations

import numpy as np

from app.history.embeddings import FaissIndexStore


def _store() -> FaissIndexStore:
    vectors = np.array([[0.0, 0.0], [1.0, 0.0], [10.0, 10.0]], dtype="float32")
    return FaissIndexStore.build([1, 2, 3], vectors)


def test_search_returns_nearest_by_id() -> None:
    store = _store()
    assert store.size == 3
    result = store.search(np.array([0.1, 0.0], dtype="float32"), k=2)
    ids = [i for i, _ in result]
    assert ids[0] == 1  # closest to [0,0]
    assert ids[1] == 2  # then [1,0]
    # distances are non-decreasing
    assert result[0][1] <= result[1][1]


def test_search_k_larger_than_index() -> None:
    store = _store()
    result = store.search(np.array([10.0, 10.0], dtype="float32"), k=50)
    assert len(result) == 3  # capped at index size
    assert result[0][0] == 3  # exact match nearest


def test_empty_index_search_returns_empty() -> None:
    store = FaissIndexStore.build([], np.zeros((0, 2), dtype="float32"))
    assert store.size == 0
    assert store.search(np.array([1.0, 1.0], dtype="float32"), k=5) == []


def test_save_load_preserves_results(tmp_path) -> None:
    store = _store()
    path = str(tmp_path / "history.index")
    store.save(path)
    loaded = FaissIndexStore.load(path)
    q = np.array([0.1, 0.0], dtype="float32")
    assert store.search(q, 3) == loaded.search(q, 3)


def test_rebuild_is_deterministic() -> None:
    q = np.array([2.0, 1.0], dtype="float32")
    a = _store().search(q, 3)
    b = _store().search(q, 3)
    assert a == b  # identical ids and distances
