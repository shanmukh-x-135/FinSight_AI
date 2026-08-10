"""Stable content identity for news stories arriving through different feeds."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime


def article_fingerprint(title: str, published_at: datetime | None) -> str:
    """Hash a normalized, date-scoped title without retaining source-specific data."""
    stored_title = title[:600]
    normalized = unicodedata.normalize("NFKC", stored_title).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE).strip()
    day = published_at.date().isoformat() if published_at is not None else "unknown"
    return hashlib.sha256(f"{day}\n{normalized}".encode()).hexdigest()
