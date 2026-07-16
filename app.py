"""
WealthBuilder Bridge — FastAPI application entry point.

Registers middleware (in outermost-first order), mounts all API routers,
configures global exception handlers, and exposes startup / shutdown lifecycle
hooks.

Run with::

    uvicorn bridge.app:app --host 0.0.0.0 --port 8000

or via the project's start script::

    python -m bridge
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from bridge.core.connection_manager import ConnectionManager
from bridge.core.exceptions import BridgeBaseException
from bridge.core.logging import configure_logging, get_logger
from bridge.core.request_context import get_request_id
from bridge.core.responses import error_response
from bridge.middleware.auth import AuthenticationMiddleware
from bridge.middleware.logging import AccessLogMiddleware
from bridge.middleware.request_id import RequestIDMiddleware
from bridge.middleware.timing import TimingMiddleware

# ---------------------------------------------------------------------------
# Bootstrap logging before any other module emits a record.
# ---------------------------------------------------------------------------

from bridge.config import settings  # noqa: E402  (import after logging setup is intentional)

configure_logging(settings.log_level)
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Lifespan context manager (replaces on_event decorators in FastAPI ≥ 0.93)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Execute startup logic before yielding, then shutdown logic after."""

    # --- Startup ---
    logger.info(
        "WealthBuilder Bridge starting.",
        extra={
            "version": settings.app_version,
            "api_version": settings.api_version,
            "environment": settings.environment,
        },
    )

    connection_manager = ConnectionManager()
    application.state.connection_manager = connection_manager
    application.state.startup_time = datetime.now(tz=timezone.utc)
    application.state.startup_monotonic = time.monotonic()

    await connection_manager.start()

    logger.info(
        "WealthBuilder Bridge ready.",
        extra={"bridge_state": connection_manager.state.value},
    )

    yield  # Application is now serving requests.

    # --- Shutdown ---
    logger.info("WealthBuilder Bridge shutting down.")
    await connection_manager.stop()
    logger.info("WealthBuilder Bridge stopped.")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description=(
        "WealthBuilder Bridge Phase 2.1 — Enterprise broker communication layer. "
        "Provides authenticated REST endpoints for broker account data, market data, "
        "position management, and trade execution. "
        "MT5 connectivity is implemented in Phase 2.2."
    ),
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware  (registered inner → outer; executes outer → inner per request)
# ---------------------------------------------------------------------------

# 1. Request ID — outermost; every subsequent middleware can read the ID.
app.add_middleware(RequestIDMiddleware)

# 2. Timing — measures end-to-end latency (wraps the business logic and auth).
app.add_middleware(TimingMiddleware)

# 3. Access logging — emits one structured log line per completed request.
app.add_middleware(AccessLogMiddleware)

# 4. Authentication — validates Bearer token for all non-exempt paths.
app.add_middleware(AuthenticationMiddleware)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

from bridge.api import account, health, history, market, positions, symbols, trade  # noqa: E402

app.include_router(health.router)
app.include_router(account.router, prefix="/api")
app.include_router(positions.router, prefix="/api")
app.include_router(symbols.router, prefix="/api")
app.include_router(market.router, prefix="/api")
app.include_router(trade.router, prefix="/api")
app.include_router(history.router, prefix="/api")

# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(BridgeBaseException)
async def bridge_exception_handler(
    request: Request, exc: BridgeBaseException
) -> JSONResponse:
    """Convert any BridgeBaseException subclass into a structured error response."""
    logger.warning(
        "Bridge exception raised.",
        extra={
            "exception_type": type(exc).__name__,
            "code": exc.code,
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(
            request_id=get_request_id(),
            code=exc.code,
            message=exc.message,
        ),
    )


@app.exception_handler(RequestValidationError)
async def request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Convert FastAPI / Pydantic request validation errors into a 422 envelope."""
    logger.warning(
        "Request validation error.",
        extra={"path": request.url.path, "errors": exc.errors()},
    )
    readable = "; ".join(
        f"{' → '.join(str(loc) for loc in err['loc'])}: {err['msg']}"
        for err in exc.errors()
    )
    return JSONResponse(
        status_code=422,
        content=error_response(
            request_id=get_request_id(),
            code="VALIDATION_ERROR",
            message=readable or "Request validation failed.",
        ),
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_handler(
    request: Request, exc: ValidationError
) -> JSONResponse:
    """Convert Pydantic model validation errors into a 422 envelope."""
    logger.warning(
        "Pydantic validation error.",
        extra={"path": request.url.path},
    )
    return JSONResponse(
        status_code=422,
        content=error_response(
            request_id=get_request_id(),
            code="VALIDATION_ERROR",
            message="Response model validation failed.",
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Catch-all handler — ensures no stack trace ever leaks to the caller."""
    logger.error(
        "Unhandled exception.",
        extra={
            "exception_type": type(exc).__name__,
            "path": request.url.path,
        },
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content=error_response(
            request_id=get_request_id(),
            code="INTERNAL_ERROR",
            message="An unexpected error occurred. Please contact support.",
        ),
    )
