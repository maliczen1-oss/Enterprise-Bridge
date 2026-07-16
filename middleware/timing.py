"""
Request timing middleware.

Measures wall-clock time for every request and exposes it in the
``X-Process-Time-Ms`` response header (milliseconds, two decimal places).

The measured duration is also stored in ``request.state.process_time_ms``
so the logging middleware can include it without re-measuring.
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

_HEADER = "X-Process-Time-Ms"


class TimingMiddleware(BaseHTTPMiddleware):
    """Attach request processing duration to each response."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1_000.0

        request.state.process_time_ms = round(elapsed_ms, 2)
        response.headers[_HEADER] = f"{elapsed_ms:.2f}"
        return response
