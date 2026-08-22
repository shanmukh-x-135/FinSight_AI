"""Deterministic, crash-safe local cache for the PostgreSQL history corpus."""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import shutil
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from app.history.constants import (
    ARTIFACT_SCHEMA_VERSION,
    INDEX_FILENAME,
    MANIFEST_FILENAME,
    NORMALIZER_FILENAME,
    generations_dir,
)
from app.history.embeddings import FaissIndexStore
from app.history.feature_engineering import (
    FEATURE_NAMES,
    FEATURE_VERSION,
    NORMALIZATION_METHOD,
    Normalizer,
    vector_from_features,
)


@dataclass(frozen=True)
class CorpusRow:
    session_id: int
    faiss_id: int
    dimension: int
    feature_version: str
    feature_vector: dict[str, float]


@dataclass(frozen=True)
class IndexCorpus:
    ids: list[int]
    vectors: list[list[float]]
    corpus_hash: str
    dimension: int
    feature_version: str

    @classmethod
    def from_rows(cls, rows: Iterable[CorpusRow]) -> "IndexCorpus":
        ordered = sorted(rows, key=lambda row: row.session_id)
        if not ordered:
            raise ValueError("History index corpus is empty")

        ids: list[int] = []
        vectors: list[list[float]] = []
        digest = hashlib.sha256()
        digest.update(struct.pack(">I", ARTIFACT_SCHEMA_VERSION))
        version_encoded = FEATURE_VERSION.encode("utf-8")
        digest.update(struct.pack(">H", len(version_encoded)))
        digest.update(version_encoded)
        for name in FEATURE_NAMES:
            encoded = name.encode("utf-8")
            digest.update(struct.pack(">H", len(encoded)))
            digest.update(encoded)

        for row in ordered:
            if row.feature_version != FEATURE_VERSION:
                raise ValueError("History feature version is incompatible")
            if row.session_id != row.faiss_id:
                raise ValueError("History embedding ID does not match its session")
            vector = vector_from_features(row.feature_vector)
            if row.dimension != len(vector) or len(vector) != len(FEATURE_NAMES):
                raise ValueError("History embedding dimension is inconsistent")
            if not all(math.isfinite(value) for value in vector):
                raise ValueError("History feature vector contains non-finite values")
            ids.append(row.session_id)
            vectors.append(vector)
            digest.update(struct.pack(">q", row.session_id))
            for value in vector:
                digest.update(struct.pack(">d", value))

        return cls(
            ids=ids,
            vectors=vectors,
            corpus_hash=digest.hexdigest(),
            dimension=len(FEATURE_NAMES),
            feature_version=FEATURE_VERSION,
        )

    def reconstruct(self) -> tuple[Normalizer, FaissIndexStore]:
        normalizer = Normalizer.fit(self.vectors)
        store = FaissIndexStore.build(self.ids, normalizer.transform_many(self.vectors))
        return normalizer, store


class HistoryArtifactCache:
    """Generation-addressed FAISS cache with process-safe atomic publication."""

    def __init__(self, corpus: IndexCorpus) -> None:
        self.corpus = corpus
        self.root = Path(generations_dir())
        self.generation = self.root / corpus.corpus_hash

    def load(self) -> tuple[Normalizer, FaissIndexStore]:
        manifest = json.loads((self.generation / MANIFEST_FILENAME).read_text())
        expected = {
            "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
            "corpus_hash": self.corpus.corpus_hash,
            "session_count": len(self.corpus.ids),
            "dimension": self.corpus.dimension,
            "feature_version": FEATURE_VERSION,
            "normalization_method": NORMALIZATION_METHOD,
        }
        if (
            not isinstance(manifest, dict)
            or set(manifest)
            != {
                *expected,
                "index_sha256",
                "normalizer_sha256",
            }
            or any(manifest.get(key) != value for key, value in expected.items())
        ):
            raise ValueError("History artifact manifest is incompatible")

        index_file = self.generation / INDEX_FILENAME
        normalizer_file = self.generation / NORMALIZER_FILENAME
        if not (
            _file_sha256(index_file) == manifest["index_sha256"]
            and _file_sha256(normalizer_file) == manifest["normalizer_sha256"]
        ):
            raise ValueError("History artifact checksum is incompatible")

        normalizer = Normalizer.load(str(normalizer_file))
        store = FaissIndexStore.load(str(index_file))
        if normalizer.mean.size != self.corpus.dimension:
            raise ValueError("History normalizer dimension is incompatible")
        if store.dim != self.corpus.dimension or store.size != len(self.corpus.ids):
            raise ValueError("History FAISS cache shape is incompatible")
        if store.ids != self.corpus.ids:
            raise ValueError("History FAISS cache IDs are incompatible")
        return normalizer, store

    def publish(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        lock_path = self.root / f".{self.corpus.corpus_hash}.lock"
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                self.load()
                return
            except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError):
                pass

            staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=self.root))
            displaced: Path | None = None
            try:
                normalizer, store = self.corpus.reconstruct()
                normalizer.save(str(staging / NORMALIZER_FILENAME))
                store.save(str(staging / INDEX_FILENAME))
                manifest = {
                    "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
                    "corpus_hash": self.corpus.corpus_hash,
                    "session_count": len(self.corpus.ids),
                    "dimension": self.corpus.dimension,
                    "feature_version": FEATURE_VERSION,
                    "normalization_method": NORMALIZATION_METHOD,
                    "index_sha256": _file_sha256(staging / INDEX_FILENAME),
                    "normalizer_sha256": _file_sha256(staging / NORMALIZER_FILENAME),
                }
                (staging / MANIFEST_FILENAME).write_text(
                    json.dumps(manifest, sort_keys=True, separators=(",", ":"))
                )
                for artifact in staging.iterdir():
                    with artifact.open("rb") as handle:
                        os.fsync(handle.fileno())
                staging_fd = os.open(staging, os.O_RDONLY)
                try:
                    os.fsync(staging_fd)
                finally:
                    os.close(staging_fd)
                if self.generation.exists():
                    displaced = self.root / (
                        f".invalid-{self.corpus.corpus_hash}-{uuid4().hex}"
                    )
                    os.replace(self.generation, displaced)
                os.replace(staging, self.generation)
                directory_fd = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
                if displaced is not None and displaced.exists():
                    shutil.rmtree(displaced)


def _file_sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()
