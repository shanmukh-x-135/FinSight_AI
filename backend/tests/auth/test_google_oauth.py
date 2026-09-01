"""Google OIDC transaction, callback, and identity-linking coverage."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.google import (
    GoogleIdentity,
    GoogleOAuthClient,
    decode_oauth_transaction,
    get_google_oauth_client,
)
from app.auth.models import AuthIdentity, User

PASSWORD = "S3curePass!"


class FakeGoogleOAuthClient:
    def __init__(self, identity: GoogleIdentity) -> None:
        self.identity = identity
        self.observed_nonce: str | None = None

    def authorization_url(self, transaction) -> str:  # type: ignore[no-untyped-def]
        return f"https://accounts.google.test/auth?state={transaction.state}"

    async def exchange_and_verify(self, code: str, nonce: str) -> GoogleIdentity:
        assert code == "verified-code"
        self.observed_nonce = nonce
        return self.identity


def _state_from_start(response) -> str:  # type: ignore[no-untyped-def]
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


async def _start(client: AsyncClient, return_to: str = "/dashboard"):
    response = await client.get(
        "/api/v1/auth/google/start",
        params={"return_to": return_to},
        follow_redirects=False,
    )
    assert response.status_code == 302
    return response


@pytest.mark.asyncio
async def test_google_start_sets_signed_transaction_and_safe_return_path(
    client: AsyncClient, test_app
) -> None:
    fake = FakeGoogleOAuthClient(
        GoogleIdentity("subject-1", "google@example.com", True)
    )
    test_app.dependency_overrides[get_google_oauth_client] = lambda: fake

    response = await _start(client, "//evil.example/steal")

    transaction_cookie = client.cookies.get("finsight_google_oauth")
    transaction = decode_oauth_transaction(transaction_cookie)
    assert transaction.return_to == "/dashboard"
    assert transaction.state == _state_from_start(response)
    assert transaction.nonce
    assert "HttpOnly" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_google_only_user_is_created_and_session_established(
    client: AsyncClient, test_app, db_session: AsyncSession
) -> None:
    fake = FakeGoogleOAuthClient(
        GoogleIdentity("google-subject", "New.User@Example.com", True)
    )
    test_app.dependency_overrides[get_google_oauth_client] = lambda: fake
    start = await _start(client, "/portfolio")

    callback = await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "verified-code", "state": _state_from_start(start)},
        follow_redirects=False,
    )

    assert callback.status_code == 303
    assert callback.headers["location"] == "/oauth/callback?returnTo=%2Fportfolio"
    assert fake.observed_nonce
    assert client.cookies.get("finsight_access")
    user = await db_session.scalar(select(User).where(User.email == "new.user@example.com"))
    assert user is not None and user.hashed_password is None
    identity = await db_session.scalar(
        select(AuthIdentity).where(AuthIdentity.provider_subject == "google-subject")
    )
    assert identity is not None and identity.user_id == user.id


@pytest.mark.asyncio
async def test_verified_google_email_links_existing_password_account_once(
    client: AsyncClient, test_app, db_session: AsyncSession
) -> None:
    email = "linked@example.com"
    await client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    fake = FakeGoogleOAuthClient(GoogleIdentity("linked-subject", email, True))
    test_app.dependency_overrides[get_google_oauth_client] = lambda: fake

    for _ in range(2):
        start = await _start(client)
        callback = await client.get(
            "/api/v1/auth/google/callback",
            params={"code": "verified-code", "state": _state_from_start(start)},
            follow_redirects=False,
        )
        assert callback.status_code == 303

    assert await db_session.scalar(select(func.count()).select_from(User)) == 1
    assert await db_session.scalar(select(func.count()).select_from(AuthIdentity)) == 1


@pytest.mark.asyncio
async def test_conflicting_subject_and_verified_email_is_rejected_without_merge(
    client: AsyncClient, test_app, db_session: AsyncSession
) -> None:
    first = FakeGoogleOAuthClient(GoogleIdentity("shared-subject", "first@example.com", True))
    test_app.dependency_overrides[get_google_oauth_client] = lambda: first
    start = await _start(client)
    await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "verified-code", "state": _state_from_start(start)},
        follow_redirects=False,
    )
    await client.post(
        "/api/v1/auth/register", json={"email": "second@example.com", "password": PASSWORD}
    )

    conflict = FakeGoogleOAuthClient(
        GoogleIdentity("shared-subject", "second@example.com", True)
    )
    test_app.dependency_overrides[get_google_oauth_client] = lambda: conflict
    second_start = await _start(client)
    response = await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "verified-code", "state": _state_from_start(second_start)},
        follow_redirects=False,
    )

    assert response.headers["location"] == "/login?oauthError=identity_conflict"
    assert await db_session.scalar(select(func.count()).select_from(User)) == 2
    assert await db_session.scalar(select(func.count()).select_from(AuthIdentity)) == 1


@pytest.mark.asyncio
async def test_provider_denial_and_invalid_state_redirect_to_safe_errors(
    client: AsyncClient, test_app
) -> None:
    fake = FakeGoogleOAuthClient(GoogleIdentity("subject", "user@example.com", True))
    test_app.dependency_overrides[get_google_oauth_client] = lambda: fake
    start = await _start(client)
    denied = await client.get(
        "/api/v1/auth/google/callback",
        params={"error": "access_denied", "state": _state_from_start(start)},
        follow_redirects=False,
    )
    assert denied.headers["location"] == "/login?oauthError=provider_denied"

    await _start(client)
    invalid = await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "verified-code", "state": "attacker-state"},
        follow_redirects=False,
    )
    assert invalid.headers["location"] == "/login?oauthError=invalid_state"


@pytest.mark.parametrize(
    ("claims", "code"),
    [
        ({"nonce": "wrong", "sub": "s", "email": "a@example.com", "email_verified": True}, "invalid_nonce"),
        ({"nonce": "expected", "email": "a@example.com", "email_verified": True}, "missing_subject"),
        ({"nonce": "expected", "sub": "s", "email_verified": True}, "missing_email"),
        ({"nonce": "expected", "sub": "s", "email": "a@example.com", "email_verified": False}, "unverified_email"),
    ],
)
def test_verified_claims_require_nonce_subject_and_verified_email(
    claims: dict, code: str
) -> None:
    from app.auth.exceptions import OAuthFlowError

    with pytest.raises(OAuthFlowError) as caught:
        GoogleOAuthClient._identity_from_claims(claims, "expected")
    assert caught.value.code == code
