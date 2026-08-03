"""Data-access layer for the auth/user domain.

Thin async wrappers around SQLAlchemy queries. No business rules here — the
service layer owns those. Keeping DB access isolated makes the service unit-
testable with a fake repository if desired.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.models import Preferences, Session, User


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

    async def create_user(self, email: str, hashed_password: str) -> User:
        """Create a user together with a default preferences row."""
        user = User(email=email, hashed_password=hashed_password)
        user.preferences = Preferences()  # defaults from the model
        self.db.add(user)
        await self.db.flush()  # assign PKs without ending the transaction
        return user

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

    async def revoke_session(self, session: Session) -> None:
        session.revoked = True
        await self.db.flush()
