"""Pydantic request/response schemas for the auth & user endpoints.

These are the API contract (validated, documented in OpenAPI). They are
deliberately separate from the ORM models — the wire shape never exposes the
password hash or internal columns.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.auth.constants import InvestmentHorizon, Market, RiskTolerance


# --------------------------------------------------------------------------- #
# Requests                                                                     #
# --------------------------------------------------------------------------- #
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128, examples=["S3curePass!"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


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


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
