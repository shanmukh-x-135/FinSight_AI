"""HTTP middleware.

The request-ID middleware assigns every request a correlation ID (honoring an
inbound ``X-Request-ID`` if the caller supplied one), binds it to the logging
context so all logs during the request carry it, and echoes it back on the
response. This is the backbone of the structured-logging story in design doc
§4.10.
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from config.constants import REQUEST_ID_HEADER
from config.logging import bind_request_id, clear_request_id


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID to every request/response and the log context."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        bind_request_id(request_id)
        # Expose it to downstream handlers via request.state as well.
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        finally:
            clear_request_id()
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
