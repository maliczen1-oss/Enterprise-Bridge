"""
ATLAS CERTIFICATION HEADER
name=middleware/auth.py
Version: 3.2.0
Change Log:
- Fixed configuration attribute mismatch and ensured token validation uses the canonical
  `AUTH_TOKEN` setting from config.py.
- Ensured request id is propagated into core.request_context so error envelopes include it.
- Returned canonical BridgeResponse error envelopes for authentication failures.
- Kept /health and other EXEMPT_PATHS unauthenticated.

Production Certification: Phase 3.2
"""

# middleware/auth.py
from __future__ import annotations

import logging
import hmac
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from core.request_context import get_request_id, set_request_id
from core.responses import error_response

logger = logging.getLogger(__name__)

# Paths that do NOT require authentication (exact prefix match).
EXEMPT_PATHS: tuple[str, ...] = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Validate Bearer tokens for all non-exempt paths and ensure request-id
    propagation so that error envelopes and logs contain the request id.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # Ensure we have a request id set for logging and error envelopes. If the
        # RequestIDMiddleware (registered earlier) has already set it, this is a no-op.
        rid = request.headers.get("X-Request-Id")
        if rid:
            set_request_id(rid)

        if self._is_exempt(request.url.path):
            return await call_next(request)

        # Deferred import to avoid circular dependencies
        from config import settings

        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            logger.warning(
                "Rejected unauthenticated request.",
                extra={"path": request.url.path, "method": request.method, "requestId": get_request_id()},
            )
            return JSONResponse(
                status_code=401,
                content=error_response(
                    request_id=get_request_id(),
                    code="AUTHENTICATION_FAILED",
                    message=(
                        "Missing or malformed Authorization header. "
                        "Expected: Authorization: Bearer <token>"
                    ),
                ),
            )

        token = auth_header.removeprefix("Bearer ")

        # Support both older lowercase attribute and canonical uppercase name to be robust
        expected = getattr(settings, "AUTH_TOKEN", None) or getattr(settings, "auth_token", None)

        if not expected or not hmac.compare_digest(token, expected):
            logger.warning(
                "Rejected request with invalid token.",
                extra={"path": request.url.path, "method": request.method, "requestId": get_request_id()},
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
