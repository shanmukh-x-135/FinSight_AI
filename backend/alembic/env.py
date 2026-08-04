"""Alembic migration environment (async).

The database URL and target metadata are pulled from the application itself
(``config.settings`` + ``app.shared.database.Base``) so migrations always target
the same database and schema the app uses. Runs migrations through the async
engine per SQLAlchemy 2.0.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool

from app.shared.database import Base
from config.settings import settings

# Import model modules so ``Base.metadata`` is fully populated for autogenerate
# and offline SQL. Add new feature models here as later phases introduce them.
from app.auth import models as _auth_models  # noqa: E402,F401
from app.market import models as _market_models  # noqa: E402,F401
from app.portfolio import models as _portfolio_models  # noqa: E402,F401
from app.history import models as _history_models  # noqa: E402,F401

config = context.config

# Inject the runtime DB URL (never hardcoded in alembic.ini).
config.set_main_option("sqlalchemy.url", settings.database_url_str)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live DB connection."""
    context.configure(
        url=settings.database_url_str,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against a live database via the async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
