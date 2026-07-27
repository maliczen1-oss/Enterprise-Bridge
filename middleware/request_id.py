"""
Request ID middleware.

Generates a UUID v4 for every inbound request, attaches it to:
  - ``request.state.request_id``  — accessible to downstream handlers
  - ``X-Request-ID`` response header — returned to the caller
  - the process-local context variable — consumed by the log formatter

If the caller supplies an ``X-Request-ID`` header it is honoured, allowing
distributed tracing to preserve correlation IDs across service boundaries.
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from core.request_context import set_request_id

_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assign a unique request ID to every request."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id: str = request.headers.get(_HEADER) or str(uuid.uuid4())

        # Propagate to request state and async context.
        request.state.request_id = request_id
        set_request_id(request_id)

        response: Response = await call_next(request)
        response.headers[_HEADER] = request_id
        return response
