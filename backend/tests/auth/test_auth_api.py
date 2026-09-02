"""Cookie-session API tests for authentication and user endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import AsyncClient

from app.auth.dependencies import ACCESS_COOKIE, REFRESH_COOKIE
from config.settings import settings

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
SESSION = "/api/v1/auth/session"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/user/me"
PREFS = "/api/v1/user/preferences"

EMAIL = "investor@example.com"
PASSWORD = "S3curePass!"


async def _register(client: AsyncClient, email: str = EMAIL, password: str = PASSWORD):
    return await client.post(REGISTER, json={"email": email, "password": password})


async def _login_session(
    client: AsyncClient, email: str = EMAIL, password: str = PASSWORD
) -> dict:
    await _register(client, email, password)
    response = await client.post(LOGIN, json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _csrf(session: dict) -> dict[str, str]:
    return {"X-CSRF-Token": session["csrf_token"]}


@pytest.mark.asyncio
async def test_response_uses_standard_envelope(client: AsyncClient) -> None:
    response = await _register(client)
    body = response.json()
    for key in ("success", "message", "data", "timestamp", "requestId"):
        assert key in body
    assert body["success"] is True
    assert response.headers.get("X-Request-ID")


@pytest.mark.asyncio
async def test_register_success_creates_default_preferences(client: AsyncClient) -> None:
    response = await _register(client)
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["email"] == EMAIL
    assert data["is_active"] is True
    assert data["preferences"] == {
        "risk_tolerance": "moderate",
        "investment_horizon": "medium",
        "preferred_market": "IN",
        "preferred_sectors": [],
    }


@pytest.mark.asyncio
async def test_register_never_returns_password_hash(client: AsyncClient) -> None:
    response = await _register(client)
    assert "hashed_password" not in response.text


@pytest.mark.asyncio
async def test_register_duplicate_email_conflicts(client: AsyncClient) -> None:
    await _register(client)
    response = await _register(client)
    assert response.status_code == 409
    assert response.json()["error"]["type"] == "email_already_exists"


@pytest.mark.asyncio
async def test_register_normalizes_email_case(client: AsyncClient) -> None:
    await _register(client, email="Mixed@Example.com")
    assert (await _register(client, email="mixed@example.com")).status_code == 409


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
    assert (await client.post(REGISTER, json=payload)).status_code == 422


@pytest.mark.asyncio
async def test_login_establishes_http_only_cookie_session(client: AsyncClient) -> None:
    session = await _login_session(client)
    assert session["user"]["email"] == EMAIL
    assert session["csrf_token"]
    assert "access_token" not in session
    assert "refresh_token" not in session
    assert client.cookies.get(ACCESS_COOKIE)
    assert client.cookies.get(REFRESH_COOKIE)


@pytest.mark.asyncio
async def test_login_cookie_security_attributes(client: AsyncClient) -> None:
    await _register(client)
    response = await client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD})
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 2
    assert all("HttpOnly" in cookie for cookie in cookies)
    assert all("SameSite=lax" in cookie for cookie in cookies)
    assert all("Path=/" in cookie for cookie in cookies)


@pytest.mark.asyncio
async def test_login_wrong_password_401(client: AsyncClient) -> None:
    await _register(client)
    response = await client.post(LOGIN, json={"email": EMAIL, "password": "wrong-pass!"})
    assert response.status_code == 401
    assert response.json()["error"]["type"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_login_unknown_email_401(client: AsyncClient) -> None:
    response = await client.post(
        LOGIN, json={"email": "nobody@example.com", "password": PASSWORD}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_session(client: AsyncClient) -> None:
    response = await client.get(ME)
    assert response.status_code == 401
    assert response.json()["error"]["type"] == "invalid_token"


@pytest.mark.asyncio
async def test_me_and_session_hydration_with_valid_cookie(client: AsyncClient) -> None:
    session = await _login_session(client)
    response = await client.get(ME)
    assert response.status_code == 200
    assert response.json()["data"]["email"] == EMAIL
    hydrated = await client.get(SESSION)
    assert hydrated.status_code == 200
    assert hydrated.json()["data"] == session


@pytest.mark.asyncio
async def test_me_with_garbage_cookie_401(client: AsyncClient) -> None:
    client.cookies.set(ACCESS_COOKIE, "garbage.token.value")
    assert (await client.get(ME)).status_code == 401


@pytest.mark.asyncio
async def test_me_with_expired_cookie_401_not_500(client: AsyncClient) -> None:
    data = (await _register(client)).json()["data"]
    past = datetime.now(tz=timezone.utc) - timedelta(minutes=1)
    expired = jwt.encode(
        {"sub": str(data["id"]), "type": "access", "iat": past, "exp": past},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    client.cookies.set(ACCESS_COOKIE, expired)
    assert (await client.get(ME)).status_code == 401


@pytest.mark.asyncio
async def test_refresh_rotates_cookies_and_csrf(client: AsyncClient) -> None:
    session = await _login_session(client)
    old_refresh = client.cookies.get(REFRESH_COOKIE)
    response = await client.post(REFRESH, headers=_csrf(session))
    assert response.status_code == 200, response.text
    refreshed = response.json()["data"]
    assert refreshed["csrf_token"] != session["csrf_token"]
    assert client.cookies.get(REFRESH_COOKIE) != old_refresh
    assert "access_token" not in refreshed


@pytest.mark.asyncio
async def test_refresh_rotation_rejects_replay_without_clearing_winner(
    client: AsyncClient,
) -> None:
    session = await _login_session(client)
    old_refresh = client.cookies.get(REFRESH_COOKIE)
    first = await client.post(REFRESH, headers=_csrf(session))
    assert first.status_code == 200
    winning_access = client.cookies.get(ACCESS_COOKIE)

    client.cookies.set(REFRESH_COOKIE, old_refresh)
    replay = await client.post(REFRESH, headers=_csrf(session))
    assert replay.status_code == 401
    assert client.cookies.get(ACCESS_COOKIE) == winning_access


@pytest.mark.asyncio
async def test_refresh_requires_csrf(client: AsyncClient) -> None:
    await _login_session(client)
    response = await client.post(REFRESH)
    assert response.status_code == 401
    assert "CSRF" in response.json()["message"]


@pytest.mark.asyncio
async def test_refresh_with_garbage_cookie_401(client: AsyncClient) -> None:
    client.cookies.set(REFRESH_COOKIE, "not.a.jwt")
    assert (await client.post(REFRESH, headers={"X-CSRF-Token": "bad"})).status_code == 401


@pytest.mark.asyncio
async def test_cookie_mutation_requires_csrf(client: AsyncClient) -> None:
    await _login_session(client)
    response = await client.put(PREFS, json={"risk_tolerance": "aggressive"})
    assert response.status_code == 401
    assert "CSRF" in response.json()["message"]


@pytest.mark.asyncio
async def test_preferences_read_and_update(client: AsyncClient) -> None:
    session = await _login_session(client)
    assert (await client.get(PREFS)).json()["data"]["risk_tolerance"] == "moderate"
    response = await client.put(
        PREFS,
        headers=_csrf(session),
        json={"risk_tolerance": "aggressive", "preferred_sectors": ["technology"]},
    )
    assert response.status_code == 200
    assert response.json()["data"]["risk_tolerance"] == "aggressive"
    assert response.json()["data"]["preferred_sectors"] == ["technology"]


@pytest.mark.asyncio
async def test_update_preferences_invalid_enum_422(client: AsyncClient) -> None:
    session = await _login_session(client)
    response = await client.put(
        PREFS, headers=_csrf(session), json={"risk_tolerance": "yolo"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_preferences_requires_auth(client: AsyncClient) -> None:
    assert (await client.get(PREFS)).status_code == 401
    assert (await client.put(PREFS, json={"risk_tolerance": "moderate"})).status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_session_and_clears_cookies(client: AsyncClient) -> None:
    session = await _login_session(client)
    response = await client.post(LOGOUT, headers=_csrf(session))
    assert response.status_code == 200
    assert client.cookies.get(ACCESS_COOKIE) is None
    assert client.cookies.get(REFRESH_COOKIE) is None
    assert (await client.get(ME)).status_code == 401


@pytest.mark.asyncio
async def test_login_rate_limited_after_max_attempts(client: AsyncClient) -> None:
    await _register(client)
    for _ in range(settings.login_rate_limit_attempts):
        response = await client.post(LOGIN, json={"email": EMAIL, "password": "wrong!"})
        assert response.status_code == 401
    blocked = await client.post(LOGIN, json={"email": EMAIL, "password": "wrong!"})
    assert blocked.status_code == 429
    assert blocked.json()["error"]["type"] == "rate_limit_exceeded"


@pytest.mark.asyncio
async def test_successful_logins_do_not_consume_failure_limit(client: AsyncClient) -> None:
    await _register(client)
    for _ in range(settings.login_rate_limit_attempts + 2):
        response = await client.post(
            LOGIN, json={"email": EMAIL, "password": PASSWORD}
        )
        assert response.status_code == 200
