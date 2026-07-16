"""
Request / response access-log middleware.

Emits a single structured log record per request containing:
  - request_id
  - http_method
  - path
  - status_code
  - duration_ms
  - client_ip

Log level is INFO for 2xx/3xx and WARNING for 4xx/5xx.
"""

from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Emit one structured access-log entry per request."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response: Response = await call_next(request)

        request_id: str = getattr(request.state, "request_id", "")
        duration_ms: float = getattr(request.state, "process_time_ms", 0.0)
        status_code: int = response.status_code
        client_ip: str = (
            request.headers.get("X-Forwarded-For", request.client.host)
            if request.client
            else "unknown"
        )

        extra = {
            "http_method": request.method,
            "path": request.url.path,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "client_ip": client_ip,
            "request_id": request_id,
        }

        if status_code >= 400:
            logger.warning("Request completed with error.", extra=extra)
        else:
            logger.info("Request completed.", extra=extra)

        return response
