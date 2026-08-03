"""Database engine, session factory, and the declarative base.

Uses SQLAlchemy 2.0's async engine (asyncpg driver). Feature modules define
their ORM models against :class:`Base`; request handlers acquire a session via
the :func:`get_db` FastAPI dependency, which guarantees the session is closed
even if the handler raises.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config.settings import settings


class Base(DeclarativeBase):
    """Declarative base every ORM model inherits from.

    Kept in one place so Alembic's autogenerate can import a single
    ``Base.metadata`` covering every module's models.
    """


def _create_engine() -> AsyncEngine:
    return create_async_engine(
        settings.database_url_str,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
    )


# Module-level engine + session factory. The engine manages its own connection
# pool and is safe to share across the whole application.
engine: AsyncEngine = _create_engine()

SessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a database session.

    The ``async with`` block ensures the session is closed (and any open
    transaction rolled back) whether the handler returns normally or raises.
    """
    async with SessionFactory() as session:
        yield session


async def dispose_engine() -> None:
    """Dispose the engine's connection pool (called on app shutdown)."""
    await engine.dispose()
