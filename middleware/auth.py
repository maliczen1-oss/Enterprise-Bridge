"""
Authentication middleware.

Enforces Bearer token validation on all routes except those listed in
``EXEMPT_PATHS``.  Exempt paths are matched against ``request.url.path``
with an exact prefix check so that sub-paths of ``/health`` (e.g.
``/health/live``) are also excluded.

On failure the middleware short-circuits the request pipeline and returns
a standard ``BridgeResponse`` error envelope without invoking any route
handler, preventing accidental data exposure.
"""

from __future__ import annotations

import logging

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from bridge.core.request_context import get_request_id
from bridge.core.responses import error_response

logger = logging.getLogger(__name__)

# Paths that do NOT require authentication (exact prefix match).
EXEMPT_PATHS: tuple[str, ...] = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Validate Bearer tokens for all non-exempt paths."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if self._is_exempt(request.url.path):
            return await call_next(request)

        from bridge.config import settings  # deferred to avoid circular import

        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            logger.warning(
                "Rejected unauthenticated request.",
                extra={"path": request.url.path, "method": request.method},
            )
            return JSONResponse(
                status_code=401,
                content=error_response(
                    request_id=get_request_id(),
                    code="AUTHENTICATION_FAILED",
                    message="Missing or malformed Authorization header. "
                    "Expected: Authorization: Bearer <token>",
                ),
            )

        token = auth_header.removeprefix("Bearer ")
        if token != settings.auth_token:
            logger.warning(
                "Rejected request with invalid token.",
                extra={"path": request.url.path, "method": request.method},
            )
            return JSONResponse(
                status_code=401,
                content=error_response(
                    request_id=get_request_id(),
                    code="AUTHENTICATION_FAILED",
                    message="Invalid bearer token.",
                ),
            )

        return await call_next(request)

    @staticmethod
    def _is_exempt(path: str) -> bool:
        return any(path == exempt or path.startswith(f"{exempt}/") for exempt in EXEMPT_PATHS)
