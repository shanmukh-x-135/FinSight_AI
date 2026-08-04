"""History-domain exceptions."""

from __future__ import annotations

from fastapi import status

from app.shared.exceptions import AppException


class IndexNotBuiltError(AppException):
    status_code = status.HTTP_409_CONFLICT
    error_type = "history_index_not_built"

    def __init__(self) -> None:
        super().__init__(
            "Historical similarity index has not been built yet. "
            "Run the rebuild job first."
        )


class InsufficientHistoryError(AppException):
    status_code = status.HTTP_409_CONFLICT
    error_type = "insufficient_history"

    def __init__(self, have: int, need: int) -> None:
        super().__init__(
            f"Not enough historical sessions to build the index "
            f"({have} available, need at least {need})."
        )


class SessionNotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    error_type = "historical_session_not_found"

    def __init__(self) -> None:
        super().__init__("No historical session found for the requested date.")
