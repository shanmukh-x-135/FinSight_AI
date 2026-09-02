"""Pydantic request/response schemas for the auth & user endpoints.

These are the API contract (validated, documented in OpenAPI). They are
deliberately separate from the ORM models — the wire shape never exposes the
password hash or internal columns.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.auth.constants import InvestmentHorizon, Market, RiskTolerance


# --------------------------------------------------------------------------- #
# Requests                                                                     #
# --------------------------------------------------------------------------- #
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128, examples=["S3curePass!"])

    _normalize_email = field_validator("email", mode="before")(
        lambda value: value.strip().lower() if isinstance(value, str) else value
    )


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    _normalize_email = field_validator("email", mode="before")(
        lambda value: value.strip().lower() if isinstance(value, str) else value
    )


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    _normalize_email = field_validator("email", mode="before")(
        lambda value: value.strip().lower() if isinstance(value, str) else value
    )


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    password: str = Field(min_length=8, max_length=128)


class PreferencesUpdate(BaseModel):
    """All fields optional — a PUT updates only what's provided."""

    risk_tolerance: RiskTolerance | None = None
    investment_horizon: InvestmentHorizon | None = None
    preferred_market: Market | None = None
    preferred_sectors: list[str] | None = None


# --------------------------------------------------------------------------- #
# Responses                                                                    #
# --------------------------------------------------------------------------- #
class PreferencesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    risk_tolerance: str
    investment_horizon: str
    preferred_market: str
    preferred_sectors: list[str]


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    is_active: bool
    is_admin: bool
    created_at: datetime
    preferences: PreferencesResponse


class SessionResponse(BaseModel):
    """Browser-safe session bootstrap; bearer credentials never enter JS."""

    user: UserResponse
    csrf_token: str


class CsrfResponse(BaseModel):
    csrf_token: str
