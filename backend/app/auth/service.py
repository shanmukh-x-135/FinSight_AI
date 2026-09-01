"""Auth business logic.

Owns the rules and transaction boundaries; delegates persistence to
``AuthRepository`` and crypto to ``app/shared/security``. Route handlers stay
thin and never touch the ORM or JWT internals directly.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.exceptions import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidTokenError,
    OAuthFlowError,
    OAuthIdentityConflictError,
)
from app.auth.google import GOOGLE_PROVIDER, GoogleIdentity
from app.auth.models import User
from app.auth.repository import AuthRepository
from app.auth.schemas import PreferencesUpdate
from app.shared.security.jwt import (
    DecodedToken,
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.shared.security.passwords import hash_password, verify_password
from app.shared.time import as_utc, utc_now


@dataclass(frozen=True)
class IssuedSession:
    user: User
    access_token: str
    refresh_token: str
    session_id: str
    csrf_token: str


def csrf_token_for_session(session_id: str) -> str:
    """Derive a session-bound CSRF token without storing another secret."""
    from config.settings import settings

    return hmac.new(
        settings.jwt_secret.encode(),
        f"finsight-csrf:{session_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


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
    async def login(self, email: str, password: str) -> IssuedSession:
        normalized_email = email.strip().lower()
        user = await self.repo.get_user_by_email(normalized_email)

        # Verify against the stored hash. When the user doesn't exist we still
        # run a throwaway verify to keep timing uniform against enumeration.
        if user is None:
            verify_password(password, _DUMMY_HASH)
            raise InvalidCredentialsError()
        if user.hashed_password is None:
            verify_password(password, _DUMMY_HASH)
            raise InvalidCredentialsError()
        if not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError()
        if not user.is_active:
            raise InvalidCredentialsError()

        return await self._issue_tokens(user)

    # ----- Google OpenID Connect -----------------------------------------
    async def login_with_google(self, google: GoogleIdentity) -> IssuedSession:
        if not google.email_verified:
            raise OAuthFlowError(
                "unverified_email", "Google has not verified this email address."
            )
        email = google.email.strip().lower()
        identity = await self.repo.get_identity(GOOGLE_PROVIDER, google.subject)
        email_user = await self.repo.get_user_by_email(email)

        if identity is not None:
            if email_user is not None and email_user.id != identity.user_id:
                raise OAuthIdentityConflictError()
            if not identity.user.is_active:
                raise OAuthFlowError("account_disabled", "This account is not active.")
            identity.provider_email = email
            return await self._issue_tokens(identity.user)

        user = email_user
        if user is not None and not user.is_active:
            raise OAuthFlowError("account_disabled", "This account is not active.")
        if user is None:
            user = await self.repo.create_user(email=email, hashed_password=None)

        try:
            await self.repo.create_identity(
                user_id=user.id,
                provider=GOOGLE_PROVIDER,
                subject=google.subject,
                email=email,
            )
            return await self._issue_tokens(user)
        except IntegrityError:
            # A duplicated callback must converge on the identity that won the
            # unique provider+subject insert; it must never create two users.
            await self.db.rollback()
            winner = await self.repo.get_identity(GOOGLE_PROVIDER, google.subject)
            if winner is None or winner.user.email != email:
                raise OAuthIdentityConflictError() from None
            return await self._issue_tokens(winner.user)

    # ----- Refresh (with rotation) ----------------------------------------
    async def refresh(self, refresh_token: str) -> IssuedSession:
        user, session_id = await self._resolve_refresh_session(refresh_token)
        session = await self.repo.get_session_for_update_by_jti(session_id)
        if session is None or session.revoked:
            raise InvalidTokenError("Refresh token has been revoked.")

        # Rotate: revoke the presented session, then issue a fresh pair.
        await self.repo.revoke_session(session)
        return await self._issue_tokens(user)

    async def csrf_for_refresh(self, refresh_token: str) -> str:
        """Return the CSRF token only while the refresh session is active."""
        _, session_id = await self._resolve_refresh_session(refresh_token)
        return csrf_token_for_session(session_id)

    async def _resolve_refresh_session(self, refresh_token: str) -> tuple[User, str]:
        try:
            decoded: DecodedToken = decode_token(refresh_token, expected_type="refresh")
        except TokenError as exc:
            raise InvalidTokenError(str(exc)) from exc

        if decoded.jti is None:
            raise InvalidTokenError("Refresh token missing session id.")

        session = await self.repo.get_session_by_jti(decoded.jti)
        if session is None or session.revoked:
            raise InvalidTokenError("Refresh token has been revoked.")
        if as_utc(session.expires_at) < utc_now():
            raise InvalidTokenError("Refresh token has expired.")

        user = await self.repo.get_user_by_id(int(decoded.subject))
        if user is None or not user.is_active:
            raise InvalidTokenError("User no longer active.")
        return user, decoded.jti

    # ----- Preferences -----------------------------------------------------
    async def update_preferences(self, user: User, changes: PreferencesUpdate) -> User:
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

    # ----- Logout ----------------------------------------------------------
    async def logout(self, session_id: str) -> None:
        session = await self.repo.get_session_by_jti(session_id)
        if session is not None and not session.revoked:
            await self.repo.revoke_session(session)
            await self.db.commit()

    # ----- Internal --------------------------------------------------------
    async def _issue_tokens(self, user: User) -> IssuedSession:
        refresh, jti = create_refresh_token(user.id)
        access = create_access_token(user.id, session_id=jti)
        decoded = decode_token(refresh, expected_type="refresh")
        await self.repo.create_session(
            user_id=user.id, jti=jti, expires_at=decoded.expires_at
        )
        await self.db.commit()
        return IssuedSession(
            user=user,
            access_token=access,
            refresh_token=refresh,
            session_id=jti,
            csrf_token=csrf_token_for_session(jti),
        )


# A well-formed Argon2 hash of a random string, used to equalize timing on the
# "user not found" path (mitigates account enumeration via response time).
_DUMMY_HASH = hash_password("finsight-timing-equalizer")
