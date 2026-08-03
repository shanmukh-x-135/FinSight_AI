"""API tests for the auth & user endpoints (full HTTP flow against SQLite)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import AsyncClient

from config.settings import settings

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
ME = "/api/v1/user/me"
PREFS = "/api/v1/user/preferences"

EMAIL = "investor@example.com"
PASSWORD = "S3curePass!"


async def _register(client: AsyncClient, email: str = EMAIL, password: str = PASSWORD):
    return await client.post(REGISTER, json={"email": email, "password": password})


async def _login_tokens(client: AsyncClient, email: str = EMAIL, password: str = PASSWORD):
    await _register(client, email, password)
    resp = await client.post(LOGIN, json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _auth_header(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


# ----- Envelope ------------------------------------------------------------
@pytest.mark.asyncio
async def test_response_uses_standard_envelope(client: AsyncClient) -> None:
    resp = await _register(client)
    body = resp.json()
    for key in ("success", "message", "data", "timestamp", "requestId"):
        assert key in body
    assert body["success"] is True
    assert resp.headers.get("X-Request-ID")


# ----- Registration --------------------------------------------------------
@pytest.mark.asyncio
async def test_register_success_creates_default_preferences(client: AsyncClient) -> None:
    resp = await _register(client)
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["email"] == EMAIL
    assert data["is_active"] is True
    prefs = data["preferences"]
    assert prefs["risk_tolerance"] == "moderate"
    assert prefs["investment_horizon"] == "medium"
    assert prefs["preferred_market"] == "IN"
    assert prefs["preferred_sectors"] == []


@pytest.mark.asyncio
async def test_register_never_returns_password_hash(client: AsyncClient) -> None:
    resp = await _register(client)
    assert "password" not in resp.text.lower() or "hashed_password" not in resp.text
    assert "hashed_password" not in resp.json()["data"]


@pytest.mark.asyncio
async def test_register_duplicate_email_conflicts(client: AsyncClient) -> None:
    await _register(client)
    resp = await _register(client)
    assert resp.status_code == 409
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["type"] == "email_already_exists"


@pytest.mark.asyncio
async def test_register_normalizes_email_case(client: AsyncClient) -> None:
    await _register(client, email="Mixed@Example.com")
    # Same address, different case → duplicate.
    resp = await _register(client, email="mixed@example.com")
    assert resp.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": PASSWORD},
        {"email": EMAIL, "password": "short"},
        {"email": EMAIL},
        {"password": PASSWORD},
    ],
)
async def test_register_validation_errors(client: AsyncClient, payload: dict) -> None:
    resp = await client.post(REGISTER, json=payload)
    assert resp.status_code == 422


# ----- Login ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_login_success_returns_token_pair(client: AsyncClient) -> None:
    tokens = await _login_tokens(client)
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password_401(client: AsyncClient) -> None:
    await _register(client)
    resp = await client.post(LOGIN, json={"email": EMAIL, "password": "wrong-pass!"})
    assert resp.status_code == 401
    assert resp.json()["error"]["type"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_login_unknown_email_401(client: AsyncClient) -> None:
    resp = await client.post(LOGIN, json={"email": "nobody@example.com", "password": PASSWORD})
    assert resp.status_code == 401
    assert resp.json()["error"]["type"] == "invalid_credentials"


# ----- Protected route -----------------------------------------------------
@pytest.mark.asyncio
async def test_me_requires_token(client: AsyncClient) -> None:
    resp = await client.get(ME)
    assert resp.status_code == 401
    assert resp.json()["error"]["type"] == "invalid_token"


@pytest.mark.asyncio
async def test_me_with_valid_token(client: AsyncClient) -> None:
    tokens = await _login_tokens(client)
    resp = await client.get(ME, headers=_auth_header(tokens["access_token"]))
    assert resp.status_code == 200
    assert resp.json()["data"]["email"] == EMAIL


@pytest.mark.asyncio
async def test_me_with_garbage_token_401(client: AsyncClient) -> None:
    resp = await client.get(ME, headers=_auth_header("garbage.token.value"))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_with_expired_token_401_not_500(client: AsyncClient) -> None:
    data = (await _register(client)).json()["data"]
    past = datetime.now(tz=timezone.utc) - timedelta(minutes=1)
    expired = jwt.encode(
        {"sub": str(data["id"]), "type": "access", "iat": past, "exp": past},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    resp = await client.get(ME, headers=_auth_header(expired))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_rejected_as_access_token(client: AsyncClient) -> None:
    tokens = await _login_tokens(client)
    # Presenting a refresh token where an access token is expected must 401.
    resp = await client.get(ME, headers=_auth_header(tokens["refresh_token"]))
    assert resp.status_code == 401


# ----- Refresh flow --------------------------------------------------------
@pytest.mark.asyncio
async def test_refresh_returns_new_tokens(client: AsyncClient) -> None:
    tokens = await _login_tokens(client)
    resp = await client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200
    new_tokens = resp.json()["data"]
    assert new_tokens["access_token"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]  # rotated


@pytest.mark.asyncio
async def test_refresh_rotation_revokes_old_token(client: AsyncClient) -> None:
    tokens = await _login_tokens(client)
    first = await client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]})
    assert first.status_code == 200
    # Reusing the now-rotated (revoked) refresh token must fail.
    replay = await client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401
    assert replay.json()["error"]["type"] == "invalid_token"


@pytest.mark.asyncio
async def test_refresh_with_access_token_401(client: AsyncClient) -> None:
    tokens = await _login_tokens(client)
    resp = await client.post(REFRESH, json={"refresh_token": tokens["access_token"]})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_with_garbage_401(client: AsyncClient) -> None:
    resp = await client.post(REFRESH, json={"refresh_token": "not.a.jwt"})
    assert resp.status_code == 401


# ----- Preferences ---------------------------------------------------------
@pytest.mark.asyncio
async def test_get_preferences_defaults(client: AsyncClient) -> None:
    tokens = await _login_tokens(client)
    resp = await client.get(PREFS, headers=_auth_header(tokens["access_token"]))
    assert resp.status_code == 200
    assert resp.json()["data"]["risk_tolerance"] == "moderate"


@pytest.mark.asyncio
async def test_update_preferences_persists(client: AsyncClient) -> None:
    tokens = await _login_tokens(client)
    headers = _auth_header(tokens["access_token"])
    resp = await client.put(
        PREFS,
        headers=headers,
        json={
            "risk_tolerance": "aggressive",
            "preferred_sectors": ["technology", "banking"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["risk_tolerance"] == "aggressive"
    assert data["preferred_sectors"] == ["technology", "banking"]
    # Unchanged field keeps its default.
    assert data["investment_horizon"] == "medium"

    # Persisted across a fresh read.
    again = await client.get(PREFS, headers=headers)
    assert again.json()["data"]["risk_tolerance"] == "aggressive"


@pytest.mark.asyncio
async def test_update_preferences_invalid_enum_422(client: AsyncClient) -> None:
    tokens = await _login_tokens(client)
    resp = await client.put(
        PREFS,
        headers=_auth_header(tokens["access_token"]),
        json={"risk_tolerance": "yolo"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_preferences_requires_auth(client: AsyncClient) -> None:
    assert (await client.get(PREFS)).status_code == 401
    assert (await client.put(PREFS, json={"risk_tolerance": "moderate"})).status_code == 401


# ----- Rate limiting -------------------------------------------------------
@pytest.mark.asyncio
async def test_login_rate_limited_after_max_attempts(client: AsyncClient) -> None:
    await _register(client)
    limit = settings.login_rate_limit_attempts
    # The first `limit` attempts are allowed (wrong password → 401)…
    for _ in range(limit):
        r = await client.post(LOGIN, json={"email": EMAIL, "password": "wrong!"})
        assert r.status_code == 401
    # …the next one is rate-limited.
    blocked = await client.post(LOGIN, json={"email": EMAIL, "password": "wrong!"})
    assert blocked.status_code == 429
    assert blocked.json()["error"]["type"] == "rate_limit_exceeded"
