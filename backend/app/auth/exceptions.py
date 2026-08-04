"""Auth-specific exceptions.

Each subclasses the shared hierarchy (``app/shared/exceptions.py``) so the global
handler renders them in the standard error envelope with the right status code.
"""

from __future__ import annotations

from fastapi import status

from app.shared.exceptions import AppException, BusinessException


class EmailAlreadyExistsError(BusinessException):
    """Registration attempted with an email that is already taken."""

    error_type = "email_already_exists"

    def __init__(self, email: str) -> None:
        super().__init__(f"An account with email '{email}' already exists.")


class InvalidCredentialsError(AppException):
    """Login failed — wrong email or password. Message stays intentionally vague."""

    status_code = status.HTTP_401_UNAUTHORIZED
    error_type = "invalid_credentials"

    def __init__(self) -> None:
        super().__init__("Incorrect email or password.")


class InvalidTokenError(AppException):
    """A JWT was missing, malformed, expired, revoked, or the wrong type."""

    status_code = status.HTTP_401_UNAUTHORIZED
    error_type = "invalid_token"

    def __init__(self, message: str = "Invalid or expired token.") -> None:
        super().__init__(message)


class AdminAccessRequiredError(AppException):
    """An authenticated non-admin attempted an operations-only action."""

    status_code = status.HTTP_403_FORBIDDEN
    error_type = "admin_access_required"

    def __init__(self) -> None:
        super().__init__("Administrator access is required.")


class RateLimitExceededError(AppException):
    """Too many login attempts from a client within the window."""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_type = "rate_limit_exceeded"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "Too many login attempts. Please try again later.",
            detail={"retryAfterSeconds": retry_after_seconds},
        )
