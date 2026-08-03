"""Auth business logic.

Owns the rules and transaction boundaries; delegates persistence to
``AuthRepository`` and crypto to ``app/shared/security``. Route handlers stay
thin and never touch the ORM or JWT internals directly.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.exceptions import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from app.auth.models import Session, User
from app.auth.repository import AuthRepository
from app.auth.schemas import PreferencesUpdate, TokenResponse
from app.shared.security.jwt import (
    DecodedToken,
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.shared.security.passwords import hash_password, verify_password


def _as_utc(dt: datetime) -> datetime:
    """Normalize a possibly-naive datetime (SQLite) to timezone-aware UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = AuthRepository(db)

    # ----- Registration ----------------------------------------------------
    async def register(self, email: str, password: str) -> User:
        normalized_email = email.strip().lower()
        existing = await self.repo.get_user_by_email(normalized_email)
        if existing is not None:
            raise EmailAlreadyExistsError(normalized_email)

        user = await self.repo.create_user(
            email=normalized_email,
            hashed_password=hash_password(password),
        )
        await self.db.commit()
        # Reload with preferences eagerly attached for the response.
        return await self.repo.get_user_by_id(user.id)  # type: ignore[return-value]

    # ----- Login -----------------------------------------------------------
    async def login(self, email: str, password: str) -> TokenResponse:
        normalized_email = email.strip().lower()
        user = await self.repo.get_user_by_email(normalized_email)

        # Verify against the stored hash. When the user doesn't exist we still
        # run a throwaway verify to keep timing uniform against enumeration.
        if user is None:
            verify_password(password, _DUMMY_HASH)
            raise InvalidCredentialsError()
        if not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError()
        if not user.is_active:
            raise InvalidCredentialsError()

        return await self._issue_tokens(user)

    # ----- Refresh (with rotation) ----------------------------------------
    async def refresh(self, refresh_token: str) -> TokenResponse:
        try:
            decoded: DecodedToken = decode_token(refresh_token, expected_type="refresh")
        except TokenError as exc:
            raise InvalidTokenError(str(exc)) from exc

        if decoded.jti is None:
            raise InvalidTokenError("Refresh token missing session id.")

        session = await self.repo.get_session_by_jti(decoded.jti)
        if session is None or session.revoked:
            raise InvalidTokenError("Refresh token has been revoked.")
        if _as_utc(session.expires_at) < datetime.now(tz=timezone.utc):
            raise InvalidTokenError("Refresh token has expired.")

        user = await self.repo.get_user_by_id(int(decoded.subject))
        if user is None or not user.is_active:
            raise InvalidTokenError("User no longer active.")

        # Rotate: revoke the presented session, then issue a fresh pair.
        await self.repo.revoke_session(session)
        return await self._issue_tokens(user)

    # ----- Preferences -----------------------------------------------------
    async def update_preferences(
        self, user: User, changes: PreferencesUpdate
    ) -> User:
        provided = changes.model_dump(exclude_unset=True)
        # Convert enum values to their plain-string storage form.
        normalized = {
            field: (value.value if hasattr(value, "value") else value)
            for field, value in provided.items()
        }
        if normalized:
            await self.repo.update_preferences(user.preferences, normalized)
            await self.db.commit()
        return await self.repo.get_user_by_id(user.id)  # type: ignore[return-value]

    # ----- Internal --------------------------------------------------------
    async def _issue_tokens(self, user: User) -> TokenResponse:
        access = create_access_token(user.id)
        refresh, jti = create_refresh_token(user.id)
        decoded = decode_token(refresh, expected_type="refresh")
        await self.repo.create_session(
            user_id=user.id, jti=jti, expires_at=decoded.expires_at
        )
        await self.db.commit()
        return TokenResponse(access_token=access, refresh_token=refresh)


# A well-formed Argon2 hash of a random string, used to equalize timing on the
# "user not found" path (mitigates account enumeration via response time).
_DUMMY_HASH = hash_password("finsight-timing-equalizer")
