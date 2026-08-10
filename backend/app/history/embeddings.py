"""FAISS index for historical-session embeddings.

The "embedding" here is the normalized feature vector itself (no neural model).
Vectors are indexed in an exact ``IndexFlatL2`` wrapped in an ``IndexIDMap`` so
each vector is addressed by its ``session_id``. Exact search + fixed inputs make
the index fully deterministic: rebuilding from the same data yields identical
rankings.

The index may be cached on disk alongside the fitted normalizer. PostgreSQL raw
vectors remain authoritative, so cache loss or corruption is recoverable.
"""

from __future__ import annotations

import os

import faiss
import numpy as np


class FaissIndexStore:
    def __init__(self, index: faiss.Index, dim: int) -> None:
        self.index = index
        self.dim = dim

    @classmethod
    def build(cls, ids: list[int], vectors: np.ndarray) -> "FaissIndexStore":
        """Build an ID-mapped L2 index from ``vectors`` keyed by ``ids``."""
        if vectors.ndim != 2:
            raise ValueError("vectors must be a 2D array")
        dim = int(vectors.shape[1])
        index = faiss.IndexIDMap(faiss.IndexFlatL2(dim))
        if len(ids):
            index.add_with_ids(
                np.ascontiguousarray(vectors, dtype="float32"),
                np.asarray(ids, dtype="int64"),
            )
        return cls(index=index, dim=dim)

    @property
    def size(self) -> int:
        return int(self.index.ntotal)

    @property
    def ids(self) -> list[int]:
        """Return persisted external IDs for cache integrity validation."""
        if not isinstance(self.index, faiss.IndexIDMap):
            raise ValueError("FAISS index is not ID-mapped")
        return [int(value) for value in faiss.vector_to_array(self.index.id_map)]

    def search(self, vector: np.ndarray, k: int) -> list[tuple[int, float]]:
        """Return up to ``k`` ``(session_id, l2_distance)`` pairs, nearest first."""
        if vector.size != self.dim:
            raise ValueError("query vector dimension does not match index")
        query = np.ascontiguousarray(vector.reshape(1, -1), dtype="float32")
        k = min(k, self.size) if self.size else 0
        if k == 0:
            return []
        distances, ids = self.index.search(query, k)
        return [
            (int(i), float(d))
            for i, d in zip(ids[0], distances[0], strict=True)
            if i != -1
        ]

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        faiss.write_index(self.index, path)

    @classmethod
    def load(cls, path: str) -> "FaissIndexStore":
        index = faiss.read_index(path)
        if not isinstance(index, faiss.IndexIDMap):
            raise ValueError("Persisted FAISS index is not ID-mapped")
        return cls(index=index, dim=index.d)
