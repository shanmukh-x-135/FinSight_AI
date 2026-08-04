"""Cross-process scheduler job locking.

PostgreSQL advisory locks prevent the same scheduled pipeline from running in
multiple application workers. SQLite (tests/local-only) uses an in-process lock
with the same non-blocking semantics.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_local_locks: dict[int, asyncio.Lock] = {}


@asynccontextmanager
async def scheduler_job_lock(
    db: AsyncSession, lock_id: int
) -> AsyncIterator[bool]:
    """Yield whether this worker acquired the named non-blocking job lock."""
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        acquired = bool(
            (
                await db.execute(
                    text("SELECT pg_try_advisory_lock(:lock_id)"),
                    {"lock_id": lock_id},
                )
            ).scalar()
        )
        try:
            yield acquired
        finally:
            if acquired:
                await db.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": lock_id},
                )
        return

    lock = _local_locks.setdefault(lock_id, asyncio.Lock())
    if lock.locked():
        yield False
        return
    await lock.acquire()
    try:
        yield True
    finally:
        lock.release()
