"""Shared pytest fixtures.

Phase 0 smoke tests run against an in-memory SQLite database (via aiosqlite) so
they are fast and require no external service in CI. The production/dev database
is Postgres (Docker Compose); the app is DB-agnostic through ``DATABASE_URL`` and
the ``get_db`` dependency, which these fixtures override.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.auth.dependencies import login_rate_limiter
from app.auth.models import User
from app.main import create_app
from app.shared.database import Base, get_db

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    """Clear the shared in-memory login rate limiter around every test."""
    login_rate_limiter.clear()
    yield
    login_rate_limiter.clear()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a session bound to a fresh in-memory database, torn down cleanly."""
    engine = create_async_engine(TEST_DATABASE_URL, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def test_app(db_session: AsyncSession):
    """The FastAPI app with the DB dependency overridden to the test session.

    Exposed as a fixture so tests can add further dependency overrides (e.g. the
    market data client) on the same instance the HTTP client uses.
    """
    app = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    yield app
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(test_app) -> AsyncGenerator[AsyncClient, None]:
    """An HTTP client wired to the (overridden) app."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def admin_headers(client: AsyncClient, db_session: AsyncSession) -> dict[str, str]:
    """Register a persisted administrator and return an authenticated header."""
    password = "S3curePass!"
    email = "admin@example.com"
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": password}
    )
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    user.is_admin = True
    await db_session.commit()
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}
