"""
ATLAS CERTIFICATION HEADER
name=api/positions.py
Version: 3.2.0
Change Log:
- Productionized positions endpoint: uses canonical response envelope, includes requestId,
  handles bridge disconnected/unavailable states without raising, and logs duration and connection state.

Production Certification: Phase 3.2
"""

# api/positions.py
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
import logging

from core import models
from services import position_service
from core.connection_manager import manager as connection_manager
from core.request_context import get_request_id
from core.responses import success_response, error_response

router = APIRouter()
logger = logging.getLogger("bridge")


@router.get("/positions", response_model=models.BridgeResponse)
async def positions(request: Request):
    request_id = get_request_id() or request.headers.get("X-Request-Id") or ""
    start = datetime.now(timezone.utc)
    try:
        state = connection_manager.get_state()
        if state != "CONNECTED":
            logger.info("Positions requested but bridge not connected - state=%s requestId=%s", state, request_id)
            return JSONResponse(status_code=200, content=error_response(request_id=request_id or str(start.timestamp()), code="BRIDGE_NOT_CONNECTED", message="Bridge is not connected. See /health for details."))

        data = position_service.get_positions()
        envelope = success_response(request_id=request_id or str(start.timestamp()), data=data)
        return JSONResponse(status_code=200, content=envelope)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unhandled exception in /positions - requestId=%s", request_id)
        envelope = error_response(request_id=request_id or str(start.timestamp()), code="INTERNAL_ERROR", message="An internal error occurred. Reference: %s" % (request_id or ""))
        return JSONResponse(status_code=500, content=envelope)
