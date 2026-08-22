"""History-domain constants and on-disk artifact paths."""

from __future__ import annotations

import os

from config.settings import settings

INDEX_FILENAME = "history.index"
NORMALIZER_FILENAME = "normalizer.json"
MANIFEST_FILENAME = "manifest.json"
ARTIFACT_SCHEMA_VERSION = 2

# Minimum indexed sessions for a usable similarity engine.
MIN_SESSIONS_TO_BUILD = 5

# Neighbour whose next-day |return| is below this counts as "neutral".
NEUTRAL_EPSILON = 0.0


def _faiss_dir() -> str:
    return os.path.join(settings.data_dir, "faiss")


def index_path() -> str:
    return os.path.join(_faiss_dir(), INDEX_FILENAME)


def normalizer_path() -> str:
    return os.path.join(_faiss_dir(), NORMALIZER_FILENAME)


def generations_dir() -> str:
    return os.path.join(_faiss_dir(), "generations")
