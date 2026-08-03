"""Structured JSON logging.

Every log record is emitted as a single JSON object so logs are machine-parseable
in production (per design doc §4.10 / §9.7). A ``contextvar`` carries the current
request ID so any log emitted while handling a request is automatically correlated
without threading the ID through every function call.

The request-ID middleware itself lives in ``app/shared/middleware.py`` and calls
:func:`bind_request_id` / :func:`clear_request_id`.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

from config.settings import settings

# Holds the request ID for the currently-executing request (per async task).
_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

# Standard LogRecord attributes we do NOT want to duplicate inside "extra".
_RESERVED_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
) | {"message", "asctime", "taskName"}


def bind_request_id(request_id: str) -> None:
    """Associate ``request_id`` with the current execution context."""
    _request_id_ctx.set(request_id)


def clear_request_id() -> None:
    """Reset the request ID once a request finishes."""
    _request_id_ctx.set(None)


def get_request_id() -> str | None:
    """Return the request ID bound to the current context, if any."""
    return _request_id_ctx.get()


class JsonFormatter(logging.Formatter):
    """Render each ``LogRecord`` as a compact JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "message": record.getMessage(),
        }

        request_id = get_request_id()
        if request_id is not None:
            payload["requestId"] = request_id

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Merge any structured "extra=..." fields passed to the logger.
        for key, value in record.__dict__.items():
            if key not in _RESERVED_ATTRS and not key.startswith("_"):
                payload[key] = value

        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Install the JSON formatter on the root logger.

    Idempotent: calling it more than once (e.g. in tests) will not stack
    duplicate handlers.
    """
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())

    # Remove any pre-existing handlers so repeated calls don't duplicate output.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

    # Uvicorn ships its own handlers; route them through ours instead.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = []
        uv_logger.propagate = True


def get_logger(name: str) -> logging.Logger:
    """Return a module-scoped logger. Thin wrapper for a consistent import site."""
    return logging.getLogger(name)
