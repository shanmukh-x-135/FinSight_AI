"""Reusable auth dependencies.

* :func:`get_current_user` — resolves the Bearer access token to a ``User``.
  Lives in the auth module (not ``shared``) so it can query the ORM; other
  feature modules import it from here without creating an import cycle, since
  auth never imports them.
* :data:`login_rate_limiter` — a small in-memory sliding-window limiter guarding
  the login endpoint against brute force. Single-instance/dev-appropriate; a
  Redis-backed limiter would replace it for multi-instance production.
"""

from __future__ import annotations

import asyncio
import hmac
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.exceptions import (
    AdminAccessRequiredError,
    InvalidTokenError,
    RateLimitExceededError,
)
from app.auth.models import User
from app.auth.repository import AuthRepository
from app.auth.service import csrf_token_for_session
from app.shared.database import get_db
from app.shared.security.jwt import TokenError, decode_token
from app.shared.time import as_utc, utc_now

# auto_error=False so a missing/blank header yields our envelope-shaped 401
# instead of FastAPI's default error body.
_bearer_scheme = HTTPBearer(auto_error=False)

ACCESS_COOKIE = "finsight_access"
REFRESH_COOKIE = "finsight_refresh"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True)
class AuthContext:
    user: User
    session_id: str | None
    via_cookie: bool


async def get_auth_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    """Resolve and validate the authoritative server-side session."""
    bearer = credentials.credentials if credentials is not None else None
    cookie_token = request.cookies.get(ACCESS_COOKIE)
    token = bearer or cookie_token
    if not token:
        raise InvalidTokenError("Missing authentication token.")

    try:
        decoded = decode_token(token, expected_type="access")
    except TokenError as exc:
        raise InvalidTokenError(str(exc)) from exc

    repo = AuthRepository(db)
    user = await repo.get_user_by_id(int(decoded.subject))
    if user is None or not user.is_active:
        raise InvalidTokenError("User not found or inactive.")

    via_cookie = bearer is None
    if decoded.jti is not None:
        session = await repo.get_session_by_jti(decoded.jti)
        if (
            session is None
            or session.revoked
            or session.user_id != user.id
            or as_utc(session.expires_at) < utc_now()
        ):
            raise InvalidTokenError("Session is no longer active.")

    if via_cookie and request.method in UNSAFE_METHODS:
        if decoded.jti is None:
            raise InvalidTokenError("Cookie session is not bound to a server session.")
        supplied = request.headers.get("X-CSRF-Token", "")
        expected = csrf_token_for_session(decoded.jti)
        if not supplied or not hmac.compare_digest(supplied, expected):
            raise InvalidTokenError("Missing or invalid CSRF token.")

    return AuthContext(user=user, session_id=decoded.jti, via_cookie=via_cookie)


async def get_current_user(
    context: AuthContext = Depends(get_auth_context),
) -> User:
    """Return the authenticated user, or raise 401 (never 500) on any problem."""
    return context.user


async def get_admin_user(user: User = Depends(get_current_user)) -> User:
    """Return the authenticated administrator, or raise an envelope-shaped 403."""
    if not user.is_admin:
        raise AdminAccessRequiredError()
    return user


class SlidingWindowRateLimiter:
    """Per-key sliding-window limiter using a monotonic clock.

    Records one hit per call; raises :class:`RateLimitExceededError` once more
    than ``max_attempts`` hits fall within ``window_seconds``.
    """

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def hit(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        async with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_attempts:
                retry_after = int(self.window_seconds - (now - bucket[0])) + 1
                raise RateLimitExceededError(retry_after)
            bucket.append(now)

    def clear(self) -> None:
        """Reset all state (used between tests)."""
        self._hits.clear()


# Configured from settings at import time. Recreated lazily so tests can tweak
# settings before first use if needed.
from config.settings import settings  # noqa: E402

login_rate_limiter = SlidingWindowRateLimiter(
    max_attempts=settings.login_rate_limit_attempts,
    window_seconds=settings.login_rate_limit_window_seconds,
)
password_reset_rate_limiter = SlidingWindowRateLimiter(
    max_attempts=settings.password_reset_rate_limit_attempts,
    window_seconds=settings.password_reset_rate_limit_window_seconds,
)


async def enforce_login_rate_limit(request: Request) -> None:
    """FastAPI dependency: rate-limit login attempts by client IP."""
    client_ip = request.client.host if request.client else "unknown"
    await login_rate_limiter.hit(client_ip)


async def enforce_password_reset_rate_limit(request: Request) -> None:
    """Bound password-reset email requests without keying on account identity."""
    client_ip = request.client.host if request.client else "unknown"
    await password_reset_rate_limiter.hit(client_ip)
