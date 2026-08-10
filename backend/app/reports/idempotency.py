"""Privacy-preserving report idempotency key handling."""

from __future__ import annotations

import hashlib


def scope_idempotency_key(
    user_id: int | None, report_type: str, idempotency_key: str
) -> str:
    """Hash an opaque key within its owner and report-type namespace."""
    owner = str(user_id) if user_id is not None else "global"
    payload = f"{owner}\n{report_type}\n{idempotency_key}"
    return hashlib.sha256(payload.encode()).hexdigest()
