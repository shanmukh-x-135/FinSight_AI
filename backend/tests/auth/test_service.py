"""Service-level tests for auth edge cases not reachable through the HTTP API.

These drive ``AuthService`` directly against a real (in-memory) session to cover
defensive branches such as a deactivated account.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.exceptions import InvalidCredentialsError, InvalidTokenError
from app.auth.repository import AuthRepository
from app.auth.service import AuthService

EMAIL = "edge@example.com"
PASSWORD = "S3curePass!"


@pytest.mark.asyncio
async def test_login_rejects_deactivated_account(db_session: AsyncSession) -> None:
    service = AuthService(db_session)
    user = await service.register(EMAIL, PASSWORD)

    user.is_active = False
    await db_session.commit()

    with pytest.raises(InvalidCredentialsError):
        await service.login(EMAIL, PASSWORD)


@pytest.mark.asyncio
async def test_refresh_rejects_deactivated_account(db_session: AsyncSession) -> None:
    service = AuthService(db_session)
    user = await service.register(EMAIL, PASSWORD)
    tokens = await service.login(EMAIL, PASSWORD)

    reloaded = await AuthRepository(db_session).get_user_by_id(user.id)
    assert reloaded is not None
    reloaded.is_active = False
    await db_session.commit()

    with pytest.raises(InvalidTokenError):
        await service.refresh(tokens.refresh_token)
