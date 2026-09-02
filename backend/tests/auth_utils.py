"""Test-only helpers for exercising bearer compatibility without JS exposure."""

from httpx import AsyncClient

from app.auth.dependencies import ACCESS_COOKIE


def access_token_from_cookie(client: AsyncClient) -> str:
    token = client.cookies.get(ACCESS_COOKIE)
    assert token is not None
    return token
