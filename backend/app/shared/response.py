"""Standard API response envelope.

Every ``/api/v1`` endpoint returns the same success shape (design doc §6.5)::

    {"success": true, "message": "...", "data": {...},
     "timestamp": "...", "requestId": "..."}

The error counterpart is produced by the global handlers in
``app/shared/exceptions.py``; both share the ``success``/``message``/``timestamp``/
``requestId`` fields so clients parse one shape everywhere.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from config.logging import get_request_id


def envelope(data: Any = None, message: str = "") -> dict[str, Any]:
    """Wrap ``data`` in the standard success envelope."""
    return {
        "success": True,
        "message": message,
        "data": data,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "requestId": get_request_id(),
    }
