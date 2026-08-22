"""Cross-process scheduler job locking.

PostgreSQL advisory locks prevent the same scheduled pipeline from running in
multiple application workers. SQLite (tests/local-only) uses an in-process lock
with the same non-blocking semantics.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

_local_locks: dict[int, asyncio.Lock] = {}


def pipeline_run_lock_id(pipeline_name: str, target_trading_date: date) -> int:
    """Derive a stable signed 64-bit advisory-lock key for one logical run."""
    identity = f"{pipeline_name}:{target_trading_date.isoformat()}".encode()
    return int.from_bytes(
        hashlib.blake2b(identity, digest_size=8).digest(), "big", signed=True
    )


@asynccontextmanager
async def pipeline_run_lock(db: AsyncSession, lock_id: int) -> AsyncIterator[bool]:
    """Yield whether this worker acquired the named non-blocking job lock."""
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        # Pin a dedicated physical connection. Pipeline services commit their
        # domain transactions while the session-level advisory lock is held;
        # using ``db.execute`` directly could return that locked connection to
        # the pool at commit and later attempt to unlock on another connection.
        bound_engine = getattr(db, "bind", None)
        if isinstance(bound_engine, AsyncEngine):
            async with bound_engine.connect() as connection:
                acquired = bool(
                    (
                        await connection.execute(
                            text("SELECT pg_try_advisory_lock(:lock_id)"),
                            {"lock_id": lock_id},
                        )
                    ).scalar()
                )
                await connection.commit()
                try:
                    yield acquired
                finally:
                    if acquired:
                        await connection.execute(
                            text("SELECT pg_advisory_unlock(:lock_id)"),
                            {"lock_id": lock_id},
                        )
                        await connection.commit()
            return

        # Lightweight test doubles and explicitly connection-bound sessions use
        # the established same-session path.
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


# Backward-compatible name for existing callers during the P10.1 transition.
scheduler_job_lock = pipeline_run_lock
