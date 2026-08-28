"""
ATLAS CERTIFICATION HEADER
name=api/health.py
Version: 3.2.0
Change Log:
- Production-ready health endpoint returning canonical BridgeResponse envelope.
- Uses ConnectionManager's enhanced health/capabilities model and never exposes raw exceptions.
- Returns structured connection states: CONNECTED, CONNECTING, FAILED, DISCONNECTED.
- Includes bridge version, connection state, mt5Initialized, broker provider, server summary,
  account summary (when available), lastError, reconnectCount, startupTime, uptimeSeconds, timestamp.
- Ensures /health is unauthenticated and safe for probes.

Production Certification: Phase 3.2
"""

# api/health.py
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from core import models
from core.connection_manager import manager as connection_manager
from core.request_context import get_request_id
from core.responses import success_response, error_response
from datetime import datetime, timezone
from config import settings
import logging
import uuid
import os

router = APIRouter()
logger = logging.getLogger("bridge")


@router.get("/health", response_model=models.BridgeResponse)
async def health(request: Request):
    """Report bridge health status in a canonical BridgeResponse envelope.

    This endpoint is intentionally public (no authentication) so orchestration
    systems and load balancers can probe the service. It must never raise an
    unhandled exception or return stack traces.
    """
    # Ensure a request id is present; middleware normally sets this but be
    # defensive in case /health is called outside that pipeline.
    request_id = get_request_id() or request.headers.get("X-Request-Id") or str(uuid.uuid4())

    try:
        cm_health = connection_manager.get_health() or {}
        caps = connection_manager.get_capabilities() or {}

        # Preserve explicit capability failures for operator diagnosis.
        raw_state = (cm_health.get("connectionState") or caps.get("state") or "DISCONNECTED").upper()
        if raw_state == "CONNECTED":
            connection_state = "CONNECTED"
        elif raw_state in ("CONNECTING", "INITIALIZING"):
            connection_state = "CONNECTING"
        elif raw_state in ("FAILED",):
            connection_state = "FAILED"
        elif raw_state in ("UNSUPPORTED_PLATFORM", "BACKEND_UNAVAILABLE"):
            connection_state = raw_state
        else:
            connection_state = "DISCONNECTED"

        mt5_initialized = bool(cm_health.get("mt5Initialized") or caps.get("mt5Initialized", False))

        # Terminal version / server info
        terminal_version = cm_health.get("terminalVersion") or caps.get("terminalVersion")
        server = getattr(settings, "MT5_SERVER", None)

        # Last error and reconnect metadata
        last_error = cm_health.get("lastError") or caps.get("lastError")
        reconnect_count = int(cm_health.get("reconnectCount") or 0)
        last_reconnect = cm_health.get("lastReconnect")
        startup_time = cm_health.get("startupTime")
        uptime_seconds = cm_health.get("uptimeSeconds")

        data = {
            "bridgeVersion": getattr(settings, "API_VERSION", "unknown"),
            "connectionState": connection_state,
            "mt5Initialized": mt5_initialized,
            "broker": os.environ.get("BROKER_PROVIDER", "bridge"),
            "server": server,
            "terminalVersion": terminal_version,
            "lastError": last_error,
            "reconnectCount": reconnect_count,
            "lastReconnect": last_reconnect,
            "startupTime": startup_time,
            "uptimeSeconds": uptime_seconds,
        }

        success = connection_state == "CONNECTED"

        if success:
            envelope = success_response(request_id=request_id, data=data)
            return JSONResponse(status_code=200, content=envelope)
        else:
            # For non-connected states we return a structured error envelope but keep HTTP 200
            # to avoid alarming load balancers. The error body contains actionable codes.
            msg = "Bridge not ready"
            code = "CONNECTION_NOT_READY"
            envelope = error_response(request_id=request_id, code=code, message=msg)
            envelope["data"] = data
            logger.info("Health check not ready - state=%s request_id=%s", connection_state, request_id)
            return JSONResponse(status_code=200, content=envelope)

    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected error in /health - request_id=%s", request_id)
        envelope = error_response(
            request_id=request_id,
            code="HEALTH_CHECK_FAILED",
            message="Health check failed to produce a result. Reference: %s" % request_id,
        )
        # Always return 200 with a safe envelope for health
        return JSONResponse(status_code=200, content=envelope)
