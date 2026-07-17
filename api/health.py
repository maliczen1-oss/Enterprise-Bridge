# api/health.py
from fastapi import APIRouter
from core import models
from core.connection_manager import manager as connection_manager
from datetime import datetime, timezone

router = APIRouter()

@router.get("/health", response_model=models.BridgeResponse)
async def health():
    cm_health = connection_manager.get_health()
    connection_state = cm_health.get("connectionState")
    mt5_initialized = cm_health.get("mt5Initialized", False)
    terminal_version = cm_health.get("terminalVersion")
    last_error = cm_health.get("lastError")

    # Bridge is READY when connection is CONNECTED; otherwise report FAILED but still include data
    bridge_status = "READY" if connection_state == "CONNECTED" else "FAILED" if connection_state == "FAILED" else "READY"

    data = {
        "bridgeStatus": bridge_status,
        "connectionState": connection_state,
        "mt5Initialized": mt5_initialized,
        "terminalVersion": terminal_version,
        "lastError": last_error,
    }

    envelope = {
        "success": connection_state == "CONNECTED",
        "requestId": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data if connection_state == "CONNECTED" else None,
        "error": None if connection_state == "CONNECTED" else {
            "code": "CONNECTION_NOT_READY",
            "message": "MT5 connection is not ready. See lastError for details."
        }
    }

    # When not connected, still include the data block per mission but mark success false
    if connection_state != "CONNECTED":
        envelope["data"] = data

    return envelope
