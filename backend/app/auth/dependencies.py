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
import time
from collections import defaultdict, deque

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.exceptions import InvalidTokenError, RateLimitExceededError
from app.auth.models import User
from app.auth.repository import AuthRepository
from app.shared.database import get_db
from app.shared.security.jwt import TokenError, decode_token

# auto_error=False so a missing/blank header yields our envelope-shaped 401
# instead of FastAPI's default error body.
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Return the authenticated user, or raise 401 (never 500) on any problem."""
    if credentials is None or not credentials.credentials:
        raise InvalidTokenError("Missing authentication token.")

    try:
        decoded = decode_token(credentials.credentials, expected_type="access")
    except TokenError as exc:
        raise InvalidTokenError(str(exc)) from exc

    user = await AuthRepository(db).get_user_by_id(int(decoded.subject))
    if user is None or not user.is_active:
        raise InvalidTokenError("User not found or inactive.")
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


async def enforce_login_rate_limit(request: Request) -> None:
    """FastAPI dependency: rate-limit login attempts by client IP."""
    client_ip = request.client.host if request.client else "unknown"
    await login_rate_limiter.hit(client_ip)
