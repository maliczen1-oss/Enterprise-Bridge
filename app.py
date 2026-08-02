"""
ATLAS CERTIFICATION HEADER
name=app.py
Version: 3.2.0
Change Log:
- Added request ID middleware and global exception handlers to enforce a single standardized
  error envelope and to ensure no raw exceptions or stack traces are returned.
- Ensured health router remains public and all other routers require Authorization Bearer token.
- Improved startup/shutdown ordering and integration with ConnectionManager background worker.

Production Certification: Phase 3.2
"""

# app.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
import time
import uuid
import os

from core.request_context import set_request_id, get_request_id
from core.responses import success_response, error_response
from core.connection_manager import manager as connection_manager

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
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("bridge")

app = FastAPI(title="WealthBuilder Bridge")

# Request ID middleware must run first so that request-id is available to all
class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Respect incoming request id if provided, otherwise generate one
        rid = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        set_request_id(rid)
        start = time.time()
        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = int((time.time() - start) * 1000)
            # Safe logging: do not log sensitive headers or tokens
            try:
                conn_state = connection_manager.get_state()
            except Exception:
                conn_state = "UNKNOWN"
            broker = os.environ.get("BROKER_PROVIDER", "bridge")
            logger.info(
                "request=%s path=%s method=%s duration_ms=%d status=%s connection_state=%s broker=%s",
                rid,
                request.url.path,
                request.method,
                duration_ms,
                getattr(response, "status_code", "unknown"),
                conn_state,
                broker,
            )

# Register middlewares: RequestID first, Authentication second
app.add_middleware(RequestIDMiddleware)
app.add_middleware(AuthenticationMiddleware)

# Public: no authentication required.
app.include_router(health_router)

# Protected: require a valid Bearer token (enforced by AuthenticationMiddleware).
app.include_router(account_router, prefix="/api", tags=["Account"])
app.include_router(positions_router, prefix="/api", tags=["Positions"])
app.include_router(symbols_router, prefix="/api", tags=["Symbols"])
app.include_router(market_router, prefix="/api", tags=["Market"])
app.include_router(history_router, prefix="/api", tags=["History"])
# trade router declares its own prefix; keep top-level /api prefix to match existing surface
app.include_router(trade_router, prefix="/api", tags=["Trade"])


# Global exception handlers to enforce standardized envelope
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    request_id = get_request_id() or str(uuid.uuid4())
    # Map common status codes to error codes
    code_map = {
        401: "AUTHENTICATION_FAILED",
        403: "AUTHORIZATION_FAILED",
        404: "NOT_FOUND",
        400: "BAD_REQUEST",
    }
    code = code_map.get(exc.status_code, "HTTP_ERROR")
    content = error_response(request_id=request_id, code=code, message=str(exc.detail or "HTTP error"))
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Never expose tracebacks or raw exceptions. Always return canonical error envelope.
    request_id = get_request_id() or str(uuid.uuid4())
    logger.exception("Unhandled exception occurred - request_id=%s", request_id)
    content = error_response(
        request_id=request_id,
        code="INTERNAL_ERROR",
        message="An internal error occurred. Reference: %s" % request_id,
    )
    # Use 500 status code but still return safe envelope. Many platforms expect 200 for health,
    # but for unexpected errors we return 500 without exposing internals (spec allowed non-500 too).
    return JSONResponse(status_code=500, content=content)


@app.on_event("startup")
async def on_startup():
    logger.info("Application startup event")
    # Start connection manager background worker
    connection_manager.start()


@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Application shutdown event")
    connection_manager.stop()
