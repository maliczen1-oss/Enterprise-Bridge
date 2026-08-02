"""
ATLAS CERTIFICATION HEADER
name=api/symbols.py
Version: 3.2.0
Change Log:
- Productionized symbols endpoint: canonical BridgeResponse envelope, requestId propagation,
  bridge connection checks, defensive error handling.

Production Certification: Phase 3.2
"""

# api/symbols.py
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
import logging

from core import models
from services import symbol_service
from core.connection_manager import manager as connection_manager
from core.request_context import get_request_id
from core.responses import success_response, error_response

router = APIRouter()
logger = logging.getLogger("bridge")


@router.get("/symbols", response_model=models.BridgeResponse)
async def symbols(request: Request):
    request_id = get_request_id() or request.headers.get("X-Request-Id") or ""
    start = datetime.now(timezone.utc)
    try:
        state = connection_manager.get_state()
        if state != "CONNECTED":
            logger.info("Symbols requested but bridge not connected - state=%s requestId=%s", state, request_id)
            return JSONResponse(status_code=200, content=error_response(request_id=request_id or str(start.timestamp()), code="BRIDGE_NOT_CONNECTED", message="Bridge is not connected. See /health for details."))

        data = symbol_service.get_symbols()
        envelope = success_response(request_id=request_id or str(start.timestamp()), data=data)
        return JSONResponse(status_code=200, content=envelope)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unhandled exception in /symbols - requestId=%s", request_id)
        envelope = error_response(request_id=request_id or str(start.timestamp()), code="INTERNAL_ERROR", message="An internal error occurred. Reference: %s" % (request_id or ""))
        return JSONResponse(status_code=500, content=envelope)
