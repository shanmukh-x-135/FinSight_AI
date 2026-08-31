"""Global exception hierarchy and handlers.

Design doc §6.8 requires a single global exception handler that dispatches by
type — business, validation, HTTP, and AI exceptions — each mapped to a
consistent error-response shape. Phase 0 establishes the full skeleton even
though only a couple of these types are raised yet, so later phases have a
stable contract to raise against.

The error body mirrors the success envelope (design doc §6.5) so clients parse
one shape everywhere::

    {"success": false, "message": "...", "error": {"type": "...", "detail": ...},
     "timestamp": "...", "requestId": "..."}
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.shared.time import utc_now
from config.logging import get_logger, get_request_id

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Exception hierarchy                                                          #
# --------------------------------------------------------------------------- #
class AppException(Exception):
    """Base class for all application-raised exceptions.

    Attributes
    ----------
    message:
        Human-readable message safe to return to the client.
    status_code:
        HTTP status the handler should respond with.
    error_type:
        Stable machine-readable slug (e.g. ``"business_error"``).
    detail:
        Optional structured detail (never contains secrets).
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_type: str = "app_error"

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        detail: object | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.detail = detail


class BusinessException(AppException):
    """A domain/business-rule violation (e.g. duplicate email, insufficient funds)."""

    status_code = status.HTTP_409_CONFLICT
    error_type = "business_error"


class ValidationException(AppException):
    """Application-level validation failure not caught by Pydantic."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_type = "validation_error"


class AIException(AppException):
    """An AI/LLM pipeline failure (timeout, malformed response, missing evidence).

    Raised from Phase 6 onward; defined now so the handler contract is fixed.
    """

    status_code = status.HTTP_502_BAD_GATEWAY
    error_type = "ai_error"


# --------------------------------------------------------------------------- #
# Response shaping                                                             #
# --------------------------------------------------------------------------- #
def _error_body(
    message: str, error_type: str, detail: object | None
) -> dict[str, object]:
    body: dict[str, object] = {
        "success": False,
        "message": message,
        "error": {"type": error_type},
        "timestamp": utc_now().isoformat(),
        "requestId": get_request_id(),
    }
    if detail is not None:
        body["error"] = {"type": error_type, "detail": detail}  # type: ignore[dict-item]
    return body


# --------------------------------------------------------------------------- #
# Handlers                                                                     #
# --------------------------------------------------------------------------- #
async def _app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
    log = logger.warning if exc.status_code < 500 else logger.error
    log("app_exception", extra={"error_type": exc.error_type, "detail": str(exc.detail)})
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.message, exc.error_type, exc.detail),
    )


async def _http_exception_handler(
    _: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(str(exc.detail), "http_error", None),
    )


async def _validation_exception_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder(
            _error_body(
                "Request validation failed", "validation_error", exc.errors()
            )
        ),
    )


async def _unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    # Last resort: never leak internals. Log the full error, return a generic body.
    logger.exception("unhandled_exception", extra={"error_class": type(exc).__name__})
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_body("Internal server error", "internal_error", None),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register every handler centrally on the app (not per-router)."""
    app.add_exception_handler(AppException, _app_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_exception_handler)
