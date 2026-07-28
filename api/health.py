# api/health.py
import uuid
from fastapi import APIRouter
from core import models
from core.connection_manager import manager as connection_manager
from core.request_context import get_request_id
from datetime import datetime, timezone

router = APIRouter()


@router.get("/health", response_model=models.BridgeResponse)
async def health():
    cm_health = connection_manager.get_health()
    connection_state = cm_health.get("connectionState")
    mt5_initialized = cm_health.get("mt5Initialized", False)
    terminal_version = cm_health.get("terminalVersion")
    last_error = cm_health.get("lastError")

    # Capability model from connection manager
    caps = connection_manager.get_capabilities()

    # Determine bridgeStatus with finer granularity
    if caps.get("platform") and not caps.get("mt5Supported", False):
        bridge_status = "UNSUPPORTED_PLATFORM"
    elif not caps.get("mt5Available", False):
        bridge_status = "BACKEND_UNAVAILABLE"
    elif connection_state == "CONNECTED":
        bridge_status = "READY"
    elif connection_state in ("FAILED",):
        bridge_status = "FAILED"
    else:
        bridge_status = "INITIALIZING"

    data = {
        "bridgeStatus": bridge_status,
        "connectionState": connection_state,
        "mt5Initialized": mt5_initialized,
        "terminalVersion": terminal_version,
        "lastError": last_error,
        "capabilities": caps,
    }

    success = connection_state == "CONNECTED"

    request_id = get_request_id() or str(uuid.uuid4())

    envelope = {
        "success": success,
        "requestId": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data if success else data,
        "error": None if success else {
            "code": "CONNECTION_NOT_READY",
            "message": "MT5 connection is not ready. See lastError and capabilities for details."
        }
    }

    return envelope
