"""Auth & user HTTP routes.

Two routers mounted under ``/api/v1`` by the app factory:

* ``auth_router`` → ``/api/v1/auth/{register,login,refresh}``
* ``user_router`` → ``/api/v1/user/{me,preferences}``

Handlers stay thin: validate input (Pydantic), call the service, wrap the result
in the standard success envelope. Errors bubble up as typed exceptions and are
rendered by the global handlers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import enforce_login_rate_limit, get_current_user
from app.auth.models import User
from app.auth.schemas import (
    LoginRequest,
    PreferencesResponse,
    PreferencesUpdate,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.auth.service import AuthService
from app.shared.database import get_db
from app.shared.response import envelope

auth_router = APIRouter(prefix="/auth", tags=["auth"])
user_router = APIRouter(prefix="/user", tags=["user"])


# --------------------------------------------------------------------------- #
# Auth                                                                         #
# --------------------------------------------------------------------------- #
@auth_router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Create an account with an email and password. A default "
    "preferences profile is created automatically.",
)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> dict:
    user = await AuthService(db).register(payload.email, payload.password)
    return envelope(
        data=UserResponse.model_validate(user),
        message="Registration successful.",
    )


@auth_router.post(
    "/login",
    summary="Log in and receive tokens",
    description="Exchange email/password for an access + refresh token pair. "
    "Rate-limited per client IP to deter brute-force attacks.",
    dependencies=[Depends(enforce_login_rate_limit)],
)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> dict:
    tokens: TokenResponse = await AuthService(db).login(payload.email, payload.password)
    return envelope(data=tokens, message="Login successful.")


@auth_router.post(
    "/refresh",
    summary="Rotate tokens using a refresh token",
    description="Exchange a valid, non-revoked refresh token for a new token "
    "pair. The presented refresh token is revoked (rotation).",
)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> dict:
    tokens: TokenResponse = await AuthService(db).refresh(payload.refresh_token)
    return envelope(data=tokens, message="Token refreshed.")


# --------------------------------------------------------------------------- #
# User                                                                         #
# --------------------------------------------------------------------------- #
@user_router.get(
    "/me",
    summary="Get the current authenticated user",
    description="Protected endpoint: returns the authenticated user and their "
    "preferences. Requires a valid Bearer access token.",
)
async def get_me(current_user: User = Depends(get_current_user)) -> dict:
    return envelope(data=UserResponse.model_validate(current_user))


@user_router.get(
    "/preferences",
    summary="Get the current user's preferences",
)
async def get_preferences(current_user: User = Depends(get_current_user)) -> dict:
    return envelope(data=PreferencesResponse.model_validate(current_user.preferences))


@user_router.put(
    "/preferences",
    summary="Update the current user's preferences",
    description="Partial update — only the provided fields are changed.",
)
async def update_preferences(
    payload: PreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await AuthService(db).update_preferences(current_user, payload)
    return envelope(
        data=PreferencesResponse.model_validate(user.preferences),
        message="Preferences updated.",
    )
