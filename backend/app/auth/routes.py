"""Auth & user HTTP routes.

Two routers mounted under ``/api/v1`` by the app factory:

* ``auth_router`` → ``/api/v1/auth/{register,login,refresh}``
* ``user_router`` → ``/api/v1/user/{me,preferences}``

Handlers stay thin: validate input (Pydantic), call the service, wrap the result
in the standard success envelope. Errors bubble up as typed exceptions and are
rendered by the global handlers.
"""

from __future__ import annotations

import hmac
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    AuthContext,
    enforce_login_rate_limit,
    get_auth_context,
    get_current_user,
)
from app.auth.exceptions import OAuthFlowError
from app.auth.google import (
    OAUTH_TRANSACTION_COOKIE,
    OAUTH_TRANSACTION_TTL_SECONDS,
    GoogleOAuthClient,
    create_oauth_transaction,
    decode_oauth_transaction,
    get_google_oauth_client,
)
from app.auth.models import User
from app.auth.schemas import (
    CsrfResponse,
    LoginRequest,
    PreferencesResponse,
    PreferencesUpdate,
    RegisterRequest,
    SessionResponse,
    UserResponse,
)
from app.auth.service import AuthService, IssuedSession
from app.shared.database import get_db
from app.shared.response import envelope

auth_router = APIRouter(prefix="/auth", tags=["auth"])
user_router = APIRouter(prefix="/user", tags=["user"])


def _cookie_security() -> tuple[bool, str]:
    """Cookies are same-site through the Next.js API proxy in production."""
    from config.settings import settings

    return settings.is_production, "lax"


def _set_session_cookies(response: Response, session: IssuedSession) -> None:
    from config.settings import settings

    secure, same_site = _cookie_security()
    response.set_cookie(
        ACCESS_COOKIE,
        session.access_token,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
        secure=secure,
        httponly=True,
        samesite=same_site,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        session.refresh_token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path="/",
        secure=secure,
        httponly=True,
        samesite=same_site,
    )


def _clear_session_cookies(response: Response) -> None:
    secure, same_site = _cookie_security()
    response.delete_cookie(
        ACCESS_COOKIE,
        path="/",
        secure=secure,
        httponly=True,
        samesite=same_site,
    )
    response.delete_cookie(
        REFRESH_COOKIE,
        path="/",
        secure=secure,
        httponly=True,
        samesite=same_site,
    )


def _session_payload(session: IssuedSession) -> SessionResponse:
    return SessionResponse(
        user=UserResponse.model_validate(session.user),
        csrf_token=session.csrf_token,
    )


def _clear_oauth_transaction(response: Response) -> None:
    secure, same_site = _cookie_security()
    response.delete_cookie(
        OAUTH_TRANSACTION_COOKIE,
        path="/",
        secure=secure,
        httponly=True,
        samesite=same_site,
    )


def _oauth_error_response(code: str) -> RedirectResponse:
    response = RedirectResponse(
        url=f"/login?{urlencode({'oauthError': code})}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    _clear_oauth_transaction(response)
    return response


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
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = await AuthService(db).login(payload.email, payload.password)
    _set_session_cookies(response, session)
    return envelope(data=_session_payload(session), message="Login successful.")


@auth_router.get("/google/start", summary="Start Google OpenID Connect sign-in")
async def google_start(
    return_to: str | None = None,
    google: GoogleOAuthClient = Depends(get_google_oauth_client),
) -> RedirectResponse:
    transaction, transaction_token = create_oauth_transaction(return_to)
    response = RedirectResponse(
        google.authorization_url(transaction), status_code=status.HTTP_302_FOUND
    )
    secure, same_site = _cookie_security()
    response.set_cookie(
        OAUTH_TRANSACTION_COOKIE,
        transaction_token,
        max_age=OAUTH_TRANSACTION_TTL_SECONDS,
        path="/",
        secure=secure,
        httponly=True,
        samesite=same_site,
    )
    return response


@auth_router.get("/google/callback", summary="Complete Google OpenID Connect sign-in")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
    google: GoogleOAuthClient = Depends(get_google_oauth_client),
) -> RedirectResponse:
    try:
        transaction = decode_oauth_transaction(
            request.cookies.get(OAUTH_TRANSACTION_COOKIE)
        )
        if not state or not secrets.compare_digest(state, transaction.state):
            raise OAuthFlowError("invalid_state", "Google sign-in validation failed.")
        if error:
            code_name = "provider_denied" if error == "access_denied" else "provider_error"
            raise OAuthFlowError(code_name, "Google sign-in was not completed.")
        if not code:
            raise OAuthFlowError("missing_code", "Google did not return an authorization code.")
        identity = await google.exchange_and_verify(code, transaction.nonce)
        session = await AuthService(db).login_with_google(identity)
    except OAuthFlowError as exc:
        return _oauth_error_response(exc.code)

    response = RedirectResponse(
        url=f"/oauth/callback?{urlencode({'returnTo': transaction.return_to})}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    _clear_oauth_transaction(response)
    _set_session_cookies(response, session)
    return response


@auth_router.post(
    "/refresh",
    summary="Rotate tokens using a refresh token",
    description="Exchange a valid, non-revoked refresh token for a new token "
    "pair. The presented refresh token is revoked (rotation).",
)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if not refresh_token:
        from app.auth.exceptions import InvalidTokenError

        raise InvalidTokenError("Missing refresh session.")
    service = AuthService(db)
    expected_csrf = await service.csrf_for_refresh(refresh_token)
    supplied_csrf = request.headers.get("X-CSRF-Token", "")
    if not supplied_csrf or not hmac.compare_digest(supplied_csrf, expected_csrf):
        from app.auth.exceptions import InvalidTokenError

        raise InvalidTokenError("Missing or invalid CSRF token.")
    session = await service.refresh(refresh_token)
    _set_session_cookies(response, session)
    return envelope(data=_session_payload(session), message="Session refreshed.")


@auth_router.get("/csrf", summary="Bootstrap CSRF protection for refresh")
async def get_csrf(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if not refresh_token:
        from app.auth.exceptions import InvalidTokenError

        raise InvalidTokenError("Missing refresh session.")
    csrf_token = await AuthService(db).csrf_for_refresh(refresh_token)
    return envelope(data=CsrfResponse(csrf_token=csrf_token))


@auth_router.get("/session", summary="Hydrate the current browser session")
async def get_session(context: AuthContext = Depends(get_auth_context)) -> dict:
    if context.session_id is None:
        from app.auth.exceptions import InvalidTokenError

        raise InvalidTokenError("Session is not server-bound.")
    from app.auth.service import csrf_token_for_session

    return envelope(
        data=SessionResponse(
            user=UserResponse.model_validate(context.user),
            csrf_token=csrf_token_for_session(context.session_id),
        )
    )


@auth_router.post("/logout", summary="Revoke and clear the current session")
async def logout(
    response: Response,
    context: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if context.session_id is not None:
        await AuthService(db).logout(context.session_id)
    _clear_session_cookies(response)
    return envelope(data=None, message="Logged out.")


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
