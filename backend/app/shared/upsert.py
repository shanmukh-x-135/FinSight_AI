"""Dialect-aware INSERT builder for the two supported database engines.

Production uses PostgreSQL and tests use SQLite.  Both expose SQLAlchemy's
``ON CONFLICT`` API, which lets repositories make uniqueness constraints the
atomic source of truth instead of relying on race-prone read-before-write code.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession


def conflict_insert(db: AsyncSession, model: Any) -> Any:
    """Return the supported dialect's INSERT construct for ``model``."""
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        return postgresql_insert(model)
    if dialect == "sqlite":
        return sqlite_insert(model)
    raise RuntimeError(f"Unsupported database dialect for atomic upsert: {dialect}")
