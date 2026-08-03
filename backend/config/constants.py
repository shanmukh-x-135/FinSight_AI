"""Application-wide constants.

Values here are compile-time constants shared across modules — not user- or
environment-configurable settings (those belong in ``settings.py``).
"""

from __future__ import annotations

# Header used to propagate / echo the correlation ID for a request.
REQUEST_ID_HEADER = "X-Request-ID"

# Health endpoint status strings.
HEALTH_OK = "ok"
HEALTH_DEGRADED = "degraded"
