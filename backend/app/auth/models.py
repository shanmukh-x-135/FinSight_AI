"""ORM models for the User domain and linked authentication identities.

Split into three tables per the design doc's User-domain schema (§6.3):

* ``users``        — identity + credentials.
* ``preferences``  — 1:1 personalization profile driving later report/rec logic.
* ``sessions``     — issued refresh tokens (by ``jti``) so they can be revoked
  and rotated.
* ``auth_identities`` — verified external-provider subjects linked to users.

Column types are chosen to work identically on Postgres and the SQLite test DB:
``JSON`` for the sectors list, plain strings for the preference vocabularies
(validated at the schema layer via ``app/auth/constants.py``).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.auth.constants import (
    DEFAULT_INVESTMENT_HORIZON,
    DEFAULT_MARKET,
    DEFAULT_RISK_TOLERANCE,
)
from app.shared.database import Base
from app.shared.time import utc_now


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(
        String(320), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    preferences: Mapped["Preferences"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    sessions: Mapped[list["Session"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    auth_identities: Mapped[list["AuthIdentity"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Preferences(Base):
    __tablename__ = "preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    risk_tolerance: Mapped[str] = mapped_column(
        String(20), default=DEFAULT_RISK_TOLERANCE.value, nullable=False
    )
    investment_horizon: Mapped[str] = mapped_column(
        String(20), default=DEFAULT_INVESTMENT_HORIZON.value, nullable=False
    )
    preferred_market: Mapped[str] = mapped_column(
        String(8), default=DEFAULT_MARKET.value, nullable=False
    )
    # List of sector names; JSON keeps it portable across Postgres/SQLite.
    preferred_sectors: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="preferences")


class Session(Base):
    """A server-side record of an issued refresh token, keyed by its ``jti``.

    Enables revocation and rotation: on refresh, the presented token's ``jti``
    must map to a non-revoked, non-expired row; that row is then revoked and a
    new one issued.
    """

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="sessions")


class AuthIdentity(Base):
    """One verified external-provider subject linked to one internal user."""

    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_subject", name="uq_auth_identity_provider_subject"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_email: Mapped[str] = mapped_column(String(320), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="auth_identities")
