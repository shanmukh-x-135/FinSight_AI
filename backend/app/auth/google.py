"""Google OAuth 2.0 / OpenID Connect client and transaction validation."""

from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.auth.exceptions import OAuthFlowError, OAuthUnavailableError
from app.shared.time import utc_now
from config.settings import settings

GOOGLE_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_PROVIDER = "google"
OAUTH_TRANSACTION_COOKIE = "finsight_google_oauth"
OAUTH_TRANSACTION_TTL_SECONDS = 10 * 60


@dataclass(frozen=True)
class OAuthTransaction:
    state: str
    nonce: str
    return_to: str


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str
    email_verified: bool


def google_is_configured() -> bool:
    return bool(
        settings.google_oauth_client_id
        and settings.google_oauth_client_secret
        and settings.google_oauth_redirect_uri
    )


def safe_return_to(value: str | None) -> str:
    if not value or not value.startswith("/") or value.startswith("//"):
        return "/dashboard"
    return value


def create_oauth_transaction(return_to: str | None) -> tuple[OAuthTransaction, str]:
    transaction = OAuthTransaction(
        state=secrets.token_urlsafe(32),
        nonce=secrets.token_urlsafe(32),
        return_to=safe_return_to(return_to),
    )
    issued_at = utc_now()
    token = jwt.encode(
        {
            "type": "google_oauth_transaction",
            "state": transaction.state,
            "nonce": transaction.nonce,
            "return_to": transaction.return_to,
            "iat": issued_at,
            "exp": issued_at + timedelta(seconds=OAUTH_TRANSACTION_TTL_SECONDS),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return transaction, token


def decode_oauth_transaction(token: str | None) -> OAuthTransaction:
    if not token:
        raise OAuthFlowError("missing_transaction", "Google sign-in session is missing.")
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise OAuthFlowError(
            "expired_transaction", "Google sign-in took too long. Please try again."
        ) from exc
    except jwt.PyJWTError as exc:
        raise OAuthFlowError(
            "invalid_transaction", "Google sign-in session is invalid."
        ) from exc
    if claims.get("type") != "google_oauth_transaction":
        raise OAuthFlowError("invalid_transaction", "Google sign-in session is invalid.")
    state = claims.get("state")
    nonce = claims.get("nonce")
    return_to = claims.get("return_to")
    if not all(isinstance(value, str) and value for value in (state, nonce, return_to)):
        raise OAuthFlowError("invalid_transaction", "Google sign-in session is invalid.")
    return OAuthTransaction(state=state, nonce=nonce, return_to=safe_return_to(return_to))


class GoogleOAuthClient:
    def __init__(self) -> None:
        if not google_is_configured():
            raise OAuthUnavailableError()
        self.client_id = settings.google_oauth_client_id or ""
        self.client_secret = settings.google_oauth_client_secret or ""
        self.redirect_uri = settings.google_oauth_redirect_uri or ""

    def authorization_url(self, transaction: OAuthTransaction) -> str:
        return f"{GOOGLE_AUTHORIZATION_URL}?{urlencode({
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': 'openid email',
            'state': transaction.state,
            'nonce': transaction.nonce,
            'prompt': 'select_account',
        })}"

    async def exchange_and_verify(self, code: str, nonce: str) -> GoogleIdentity:
        try:
            async with httpx.AsyncClient(
                timeout=settings.google_oauth_timeout_seconds
            ) as client:
                response = await client.post(
                    GOOGLE_TOKEN_URL,
                    data={
                        "code": code,
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "redirect_uri": self.redirect_uri,
                        "grant_type": "authorization_code",
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OAuthFlowError(
                "provider_failure", "Google could not complete sign-in. Please try again."
            ) from exc
        encoded_id_token = payload.get("id_token") if isinstance(payload, dict) else None
        if not isinstance(encoded_id_token, str) or not encoded_id_token:
            raise OAuthFlowError(
                "missing_id_token", "Google did not return a verified identity."
            )

        claims = await asyncio.to_thread(self._verify_id_token, encoded_id_token)
        return self._identity_from_claims(claims, nonce)

    @staticmethod
    def _identity_from_claims(claims: dict[str, Any], nonce: str) -> GoogleIdentity:
        if claims.get("nonce") != nonce:
            raise OAuthFlowError("invalid_nonce", "Google sign-in validation failed.")
        subject = claims.get("sub")
        email = claims.get("email")
        verified = claims.get("email_verified") is True
        if not isinstance(subject, str) or not subject:
            raise OAuthFlowError("missing_subject", "Google identity is incomplete.")
        if not isinstance(email, str) or not email:
            raise OAuthFlowError("missing_email", "Google did not provide an email address.")
        if not verified:
            raise OAuthFlowError(
                "unverified_email", "Google has not verified this email address."
            )
        return GoogleIdentity(
            subject=subject,
            email=email.strip().lower(),
            email_verified=True,
        )

    def _verify_id_token(self, encoded_id_token: str) -> dict[str, Any]:
        try:
            return dict(
                google_id_token.verify_oauth2_token(
                    encoded_id_token,
                    google_requests.Request(),
                    audience=self.client_id,
                )
            )
        except (ValueError, GoogleAuthError) as exc:
            raise OAuthFlowError("invalid_id_token", "Google identity validation failed.") from exc


def get_google_oauth_client() -> GoogleOAuthClient:
    return GoogleOAuthClient()
