"""JWT access/refresh token utilities.

Pure encode/decode helpers with no database or FastAPI coupling, so they are
trivially unit-testable. Two token types are issued:

* **access**  — short-lived (``access_token_expire_minutes``), sent as a Bearer
  token on every authenticated request.
* **refresh** — long-lived (``refresh_token_expire_days``), carries a unique
  ``jti`` so it can be tracked and revoked server-side (see the ``sessions``
  table). Refresh tokens are rotated on use.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt

from app.shared.time import utc_now
from config.settings import settings

TokenType = Literal["access", "refresh"]


class TokenError(Exception):
    """Raised when a token is invalid, expired, or of the wrong type."""


@dataclass(frozen=True)
class DecodedToken:
    """The validated claims we care about from a decoded token."""

    subject: str          # user id as a string
    token_type: TokenType
    jti: str | None       # present on refresh tokens
    expires_at: datetime


def _now() -> datetime:
    return utc_now()


def _create_token(
    subject: str | int,
    token_type: TokenType,
    expires_delta: timedelta,
    jti: str | None = None,
) -> str:
    issued_at = _now()
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "iat": issued_at,
        "exp": issued_at + expires_delta,
    }
    if jti is not None:
        payload["jti"] = jti
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str | int) -> str:
    """Issue a short-lived access token for ``subject`` (user id)."""
    return _create_token(
        subject,
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(subject: str | int) -> tuple[str, str]:
    """Issue a long-lived refresh token. Returns ``(token, jti)``.

    The ``jti`` is stored in the ``sessions`` table so the token can be revoked
    and rotated.
    """
    jti = uuid.uuid4().hex
    token = _create_token(
        subject,
        "refresh",
        timedelta(days=settings.refresh_token_expire_days),
        jti=jti,
    )
    return token, jti


def decode_token(token: str, expected_type: TokenType | None = None) -> DecodedToken:
    """Decode and validate a token, enforcing signature and expiry.

    Raises :class:`TokenError` on any failure (bad signature, expired, wrong
    type, missing claims) so callers never see a raw PyJWT exception.
    """
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("Invalid token") from exc

    subject = claims.get("sub")
    token_type = claims.get("type")
    if not subject or token_type not in ("access", "refresh"):
        raise TokenError("Malformed token claims")
    if expected_type is not None and token_type != expected_type:
        raise TokenError(f"Expected a {expected_type} token")

    return DecodedToken(
        subject=subject,
        token_type=token_type,
        jti=claims.get("jti"),
        expires_at=datetime.fromtimestamp(claims["exp"], tz=timezone.utc),
    )
