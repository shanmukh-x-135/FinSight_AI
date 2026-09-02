"""Data-access layer for the auth/user domain.

Thin async wrappers around SQLAlchemy queries. No business rules here — the
service layer owns those. Keeping DB access isolated makes the service unit-
testable with a fake repository if desired.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.models import (
    AuthIdentity,
    PasswordResetToken,
    Preferences,
    Session,
    User,
)
from app.shared.time import utc_now


class AuthRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ----- Users -----------------------------------------------------------
    async def get_user_by_email(self, email: str) -> User | None:
        result = await self.db.execute(
            select(User)
            .where(User.email == email)
            .options(selectinload(User.preferences))
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: int) -> User | None:
        result = await self.db.execute(
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.preferences))
        )
        return result.scalar_one_or_none()

    async def create_user(self, email: str, hashed_password: str | None) -> User:
        """Create a user together with a default preferences row."""
        user = User(email=email, hashed_password=hashed_password)
        user.preferences = Preferences()  # defaults from the model
        self.db.add(user)
        await self.db.flush()  # assign PKs without ending the transaction
        return user

    # ----- External identities -------------------------------------------
    async def get_identity(self, provider: str, subject: str) -> AuthIdentity | None:
        result = await self.db.execute(
            select(AuthIdentity)
            .where(
                AuthIdentity.provider == provider,
                AuthIdentity.provider_subject == subject,
            )
            .options(selectinload(AuthIdentity.user).selectinload(User.preferences))
        )
        return result.scalar_one_or_none()

    async def create_identity(
        self,
        *,
        user_id: int,
        provider: str,
        subject: str,
        email: str,
    ) -> AuthIdentity:
        identity = AuthIdentity(
            user_id=user_id,
            provider=provider,
            provider_subject=subject,
            provider_email=email,
        )
        self.db.add(identity)
        await self.db.flush()
        return identity

    # ----- Preferences -----------------------------------------------------
    async def update_preferences(
        self, preferences: Preferences, changes: dict[str, object]
    ) -> Preferences:
        for field, value in changes.items():
            setattr(preferences, field, value)
        await self.db.flush()
        return preferences

    # ----- Sessions (refresh tokens) --------------------------------------
    async def create_session(
        self, user_id: int, jti: str, expires_at: datetime
    ) -> Session:
        session = Session(user_id=user_id, jti=jti, expires_at=expires_at)
        self.db.add(session)
        await self.db.flush()
        return session

    async def get_session_by_jti(self, jti: str) -> Session | None:
        result = await self.db.execute(select(Session).where(Session.jti == jti))
        return result.scalar_one_or_none()

    async def get_session_for_update_by_jti(self, jti: str) -> Session | None:
        """Serialize refresh-token rotation on PostgreSQL."""
        result = await self.db.execute(
            select(Session)
            .where(Session.jti == jti)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def revoke_session(self, session: Session) -> None:
        session.revoked = True
        await self.db.flush()

    async def revoke_user_sessions(self, user_id: int) -> None:
        await self.db.execute(
            update(Session)
            .where(Session.user_id == user_id, Session.revoked.is_(False))
            .values(revoked=True)
        )

    # ----- Password reset -------------------------------------------------
    async def invalidate_password_reset_tokens(self, user_id: int) -> None:
        await self.db.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=utc_now())
        )

    async def create_password_reset_token(
        self, *, user_id: int, token_hash: str, expires_at: datetime
    ) -> PasswordResetToken:
        token = PasswordResetToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.db.add(token)
        await self.db.flush()
        return token

    async def get_password_reset_token(self, token_hash: str) -> PasswordResetToken | None:
        result = await self.db.execute(
            select(PasswordResetToken)
            .where(PasswordResetToken.token_hash == token_hash)
            .options(selectinload(PasswordResetToken.user))
        )
        return result.scalar_one_or_none()
