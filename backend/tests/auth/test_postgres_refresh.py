"""PostgreSQL proof that rotating one refresh token has exactly one winner."""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.exceptions import InvalidTokenError
from app.auth.models import User
from app.auth.service import AuthService, IssuedSession


@pytest.mark.asyncio
async def test_concurrent_refresh_rotation_has_one_winner() -> None:
    database_url = os.environ.get("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_URL is required for PostgreSQL integration")

    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    email = f"refresh-race-{uuid.uuid4().hex}@example.com"
    try:
        async with sessions() as setup:
            service = AuthService(setup)
            await service.register(email, "S3curePass!")
            issued = await service.login(email, "S3curePass!")

        async def rotate() -> IssuedSession | InvalidTokenError:
            async with sessions() as db:
                try:
                    return await AuthService(db).refresh(issued.refresh_token)
                except InvalidTokenError as exc:
                    return exc

        results = await asyncio.gather(rotate(), rotate())
        assert sum(isinstance(result, IssuedSession) for result in results) == 1
        assert sum(isinstance(result, InvalidTokenError) for result in results) == 1
    finally:
        async with sessions() as cleanup:
            await cleanup.execute(delete(User).where(User.email == email))
            await cleanup.commit()
        await engine.dispose()
