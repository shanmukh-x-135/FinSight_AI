"""Shared timezone normalization primitives."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return an aware UTC timestamp for ORM defaults and control-plane state."""
    return datetime.now(tz=timezone.utc)


def as_utc(value: datetime) -> datetime:
    """Normalize a naive-or-aware timestamp to aware UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
