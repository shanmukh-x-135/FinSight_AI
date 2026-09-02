"""Password recovery API, delivery, expiry, and session-revocation tests."""

from __future__ import annotations

from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import PasswordResetToken, Session
from app.auth.password_reset import (
    PasswordResetDeliveryError,
    get_password_reset_mailer,
)
from app.shared.time import utc_now

EMAIL = "recover@example.com"
PASSWORD = "S3curePass!"
NEW_PASSWORD = "New-S3curePass!"


class CapturingMailer:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[dict[str, str]] = []

    async def send(self, *, email: str, token: str, idempotency_key: str) -> None:
        if self.fail:
            raise PasswordResetDeliveryError()
        self.messages.append(
            {"email": email, "token": token, "idempotency_key": idempotency_key}
        )


async def _register_and_login(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD}
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_forgot_password_is_generic_for_unknown_email(
    client: AsyncClient, test_app
) -> None:
    mailer = CapturingMailer()
    test_app.dependency_overrides[get_password_reset_mailer] = lambda: mailer

    response = await client.post(
        "/api/v1/auth/password/forgot", json={"email": "missing@example.com"}
    )

    assert response.status_code == 202
    assert "eligible account" in response.json()["message"]
    assert mailer.messages == []


@pytest.mark.asyncio
async def test_password_reset_is_single_use_and_revokes_existing_sessions(
    client: AsyncClient, test_app, db_session: AsyncSession
) -> None:
    await _register_and_login(client)
    mailer = CapturingMailer()
    test_app.dependency_overrides[get_password_reset_mailer] = lambda: mailer

    requested = await client.post(
        "/api/v1/auth/password/forgot", json={"email": f"  {EMAIL.upper()}  "}
    )
    assert requested.status_code == 202
    assert len(mailer.messages) == 1
    raw_token = mailer.messages[0]["token"]
    stored = await db_session.scalar(select(PasswordResetToken))
    assert stored is not None
    assert stored.token_hash != raw_token

    reset = await client.post(
        "/api/v1/auth/password/reset",
        json={"token": raw_token, "password": NEW_PASSWORD},
    )
    assert reset.status_code == 200
    assert all(session.revoked for session in (await db_session.scalars(select(Session))).all())

    replay = await client.post(
        "/api/v1/auth/password/reset",
        json={"token": raw_token, "password": "Another-S3curePass!"},
    )
    assert replay.status_code == 400
    assert replay.json()["error"]["type"] == "invalid_password_reset_token"
    assert (
        await client.post(
            "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/login", json={"email": EMAIL, "password": NEW_PASSWORD}
        )
    ).status_code == 200


@pytest.mark.asyncio
async def test_expired_reset_token_is_rejected(
    client: AsyncClient, test_app, db_session: AsyncSession
) -> None:
    await _register_and_login(client)
    mailer = CapturingMailer()
    test_app.dependency_overrides[get_password_reset_mailer] = lambda: mailer
    await client.post("/api/v1/auth/password/forgot", json={"email": EMAIL})
    stored = await db_session.scalar(select(PasswordResetToken))
    assert stored is not None
    stored.expires_at = utc_now() - timedelta(minutes=1)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/password/reset",
        json={"token": mailer.messages[0]["token"], "password": NEW_PASSWORD},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_delivery_failure_keeps_generic_response(
    client: AsyncClient, test_app
) -> None:
    await _register_and_login(client)
    test_app.dependency_overrides[get_password_reset_mailer] = lambda: CapturingMailer(
        fail=True
    )

    response = await client.post(
        "/api/v1/auth/password/forgot", json={"email": EMAIL}
    )

    assert response.status_code == 202
    assert "eligible account" in response.json()["message"]


@pytest.mark.asyncio
async def test_forgot_password_is_rate_limited(client: AsyncClient, test_app) -> None:
    test_app.dependency_overrides[get_password_reset_mailer] = lambda: CapturingMailer()
    for index in range(3):
        response = await client.post(
            "/api/v1/auth/password/forgot",
            json={"email": f"unknown-{index}@example.com"},
        )
        assert response.status_code == 202

    blocked = await client.post(
        "/api/v1/auth/password/forgot", json={"email": "unknown-4@example.com"}
    )
    assert blocked.status_code == 429
