"""Password-reset email delivery through Resend's transactional API."""

from __future__ import annotations

from html import escape
from typing import Protocol
from urllib.parse import quote

import httpx

from app.auth.exceptions import PasswordResetUnavailableError
from config.settings import settings

RESEND_EMAILS_URL = "https://api.resend.com/emails"


class PasswordResetMailer(Protocol):
    async def send(self, *, email: str, token: str, idempotency_key: str) -> None: ...


class PasswordResetDeliveryError(Exception):
    pass


class ResendPasswordResetMailer:
    def __init__(self) -> None:
        if not settings.resend_api_key or not settings.password_reset_from_email:
            raise PasswordResetUnavailableError()

    async def send(self, *, email: str, token: str, idempotency_key: str) -> None:
        reset_url = (
            f"{settings.frontend_url.rstrip('/')}/reset-password?token={quote(token)}"
        )
        text = (
            "Reset your FinSight AI password using this secure link:\n\n"
            f"{reset_url}\n\n"
            f"This link expires in {settings.password_reset_expire_minutes} minutes. "
            "If you did not request it, you can ignore this email."
        )
        html = (
            "<h1>Reset your FinSight AI password</h1>"
            "<p>Use the secure link below to choose a new password.</p>"
            f'<p><a href="{escape(reset_url, quote=True)}">Reset password</a></p>'
            f"<p>This link expires in {settings.password_reset_expire_minutes} minutes. "
            "If you did not request it, you can ignore this email.</p>"
        )
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    RESEND_EMAILS_URL,
                    headers={
                        "Authorization": f"Bearer {settings.resend_api_key}",
                        "Idempotency-Key": idempotency_key,
                    },
                    json={
                        "from": settings.password_reset_from_email,
                        "to": [email],
                        "subject": "Reset your FinSight AI password",
                        "text": text,
                        "html": html,
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PasswordResetDeliveryError() from exc


def get_password_reset_mailer() -> PasswordResetMailer:
    return ResendPasswordResetMailer()
