"""
ATLAS CERTIFICATION HEADER
name=app.py
Version: 3.3.0
Change Log:
- Added OpenAPI Bearer authentication security scheme so Swagger UI exposes
  the Authorize button for protected API routes.
- Marked /api/* operations as requiring Bearer authentication in OpenAPI.
- Preserved /health, /docs, /redoc, and /openapi.json as public endpoints.
- Preserved request ID middleware and standardized error envelopes.
- Preserved AuthenticationMiddleware and existing authentication behaviour.
- Preserved existing router registration and public API contract.
- Preserved ConnectionManager startup/shutdown lifecycle.

Production Certification: Phase 3.3
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from core.connection_manager import manager as connection_manager
from core.request_context import get_request_id, set_request_id
from core.responses import error_response

# Routers
from api.health import router as health_router
from api.account import router as account_router
from api.positions import router as positions_router
from api.symbols import router as symbols_router
from api.market import router as market_router
from api.history import router as history_router
from api.trade import router as trade_router

# Authentication middleware
from middleware.auth import AuthenticationMiddleware


logger = logging.getLogger("bridge")


app = FastAPI(
    title="WealthBuilder Bridge",
    version="0.1.0",
    description="WealthBuilder Enterprise Bridge API",
)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Attach or generate a request ID for every request.

    The request ID is stored in the request context so that standardized
    BridgeResponse error envelopes and application logs can reference it.
    """

    async def dispatch(self, request: Request, call_next):
        # Respect an incoming request ID where supplied, otherwise generate one.
        rid = request.headers.get("X-Request-Id") or str(uuid.uuid4())

        set_request_id(rid)

        start = time.time()

        response = None

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            return response

        finally:
            duration_ms = int((time.time() - start) * 1000)

            try:
                conn_state = connection_manager.get_state()
            except Exception:
                conn_state = "UNKNOWN"

            broker = os.environ.get("BROKER_PROVIDER", "bridge")

            logger.info(
                "request=%s path=%s method=%s duration_ms=%d status=%s "
                "connection_state=%s broker=%s",
                rid,
                request.url.path,
                request.method,
                duration_ms,
                getattr(response, "status_code", "unknown"),
                conn_state,
                broker,
            )


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
#
# RequestIDMiddleware is registered before AuthenticationMiddleware in source
# order so request context is established for protected requests.
#
# AuthenticationMiddleware itself remains responsible for validating:
#
#     Authorization: Bearer <token>
#
# against config.settings.AUTH_TOKEN.
#
app.add_middleware(AuthenticationMiddleware)
app.add_middleware(RequestIDMiddleware)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
#
# Public router.
# AuthenticationMiddleware explicitly exempts /health.
#
app.include_router(health_router)


# Protected API routers.
#
# AuthenticationMiddleware protects these routes at runtime.
#
app.include_router(
    account_router,
    prefix="/api",
    tags=["Account"],
)

app.include_router(
    positions_router,
    prefix="/api",
    tags=["Positions"],
)

app.include_router(
    symbols_router,
    prefix="/api",
    tags=["Symbols"],
)

app.include_router(
    market_router,
    prefix="/api",
    tags=["Market"],
)

app.include_router(
    history_router,
    prefix="/api",
    tags=["History"],
)

# trade router declares its own route prefix.
# Preserve the existing top-level /api prefix to maintain the API contract.
app.include_router(
    trade_router,
    prefix="/api",
    tags=["Trade"],
)


# ---------------------------------------------------------------------------
# OpenAPI / Swagger authentication configuration
# ---------------------------------------------------------------------------
#
# Runtime authentication is implemented by middleware/auth.py.
#
# FastAPI does not automatically know that middleware requires a Bearer token.
# Therefore Swagger previously had no "Authorize" button.
#
# This custom OpenAPI schema declares the same Bearer authentication contract
# without introducing a second authentication mechanism.
#
# Runtime authentication remains exclusively handled by AuthenticationMiddleware.
# ---------------------------------------------------------------------------

def custom_openapi() -> Dict[str, Any]:
    """
    Generate the OpenAPI schema with the Bridge Bearer authentication scheme.

    Runtime authentication remains in middleware/auth.py.

    This function only describes the existing authentication contract to
    Swagger/OpenAPI so that Swagger UI displays the Authorize button and sends:

        Authorization: Bearer <token>

    to protected /api/* operations.
    """

    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # Ensure components exists.
    components = openapi_schema.setdefault("components", {})

    # Declare the same Bearer authentication expected by middleware/auth.py.
    security_schemes = components.setdefault("securitySchemes", {})

    security_schemes["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
    }

    # Apply Bearer authentication only to protected API operations.
    #
    # /health remains public.
    # /docs, /redoc and /openapi.json remain public.
    #
    # Every API route under /api is protected by AuthenticationMiddleware.
    paths = openapi_schema.get("paths", {})

    for path, path_item in paths.items():
        if not path.startswith("/api"):
            continue

        if not isinstance(path_item, dict):
            continue

        for operation_name, operation in path_item.items():
            # Only modify actual OpenAPI operations.
            if operation_name not in {
                "get",
                "post",
                "put",
                "patch",
                "delete",
                "options",
                "head",
                "trace",
            }:
                continue

            if not isinstance(operation, dict):
                continue

            operation["security"] = [
                {
                    "BearerAuth": [],
                }
            ]

    app.openapi_schema = openapi_schema

    return app.openapi_schema


app.openapi = custom_openapi


# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
):
    """
    Convert Starlette/FastAPI HTTP exceptions into the canonical
    BridgeResponse error envelope.
    """

    request_id = get_request_id() or str(uuid.uuid4())

    code_map = {
        400: "BAD_REQUEST",
        401: "AUTHENTICATION_FAILED",
        403: "AUTHORIZATION_FAILED",
        404: "NOT_FOUND",
    }

    code = code_map.get(
        exc.status_code,
        "HTTP_ERROR",
    )

    content = error_response(
        request_id=request_id,
        code=code,
        message=str(exc.detail or "HTTP error"),
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=content,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
):
    """
    Global safety handler.

    Never expose raw exception messages, tracebacks, credentials,
    broker information, or internal implementation details to clients.
    """

    request_id = get_request_id() or str(uuid.uuid4())

    logger.exception(
        "Unhandled exception occurred - request_id=%s",
        request_id,
    )

    content = error_response(
        request_id=request_id,
        code="INTERNAL_ERROR",
        message=(
            "An internal error occurred. "
            "Reference: %s" % request_id
        ),
    )

    return JSONResponse(
        status_code=500,
        content=content,
    )


# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def on_startup():
    """
    Start the connection manager background worker.
    """

    logger.info("Application startup event")

    connection_manager.start()


@app.on_event("shutdown")
async def on_shutdown():
    """
    Stop the connection manager cleanly during application shutdown.
    """

    logger.info("Application shutdown event")

    connection_manager.stop()
