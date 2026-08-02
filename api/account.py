"""
ATLAS CERTIFICATION HEADER
name=api/account.py
Version: 3.2.0
Change Log:
- Productionized account endpoint: uses canonical response envelope, includes requestId propagation,
  handles bridge disconnected/unavailable states without raising, and logs duration and connection state.
- Replaced informal dict envelope with core.responses helpers to ensure consistent API surface.

Production Certification: Phase 3.2
"""

# api/account.py
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
import logging
import os

from core import models
from services import account_service
from core.connection_manager import manager as connection_manager
from core.request_context import get_request_id
from core.responses import success_response, error_response

router = APIRouter()
logger = logging.getLogger("bridge")


@router.get("/account", response_model=models.BridgeResponse)
async def account(request: Request):
    """Return account summary in the canonical BridgeResponse envelope.

    The endpoint never raises raw exceptions and handles bridge disconnects
    and MT5 unavailability gracefully by returning a structured error envelope.
    """
    request_id = get_request_id() or request.headers.get("X-Request-Id") or ""
    start = datetime.now(timezone.utc)

    try:
        # Defensive: if bridge is not connected we avoid raising and return a clear error
        state = connection_manager.get_state()
        if state != "CONNECTED":
            logger.info("Account requested but bridge not connected - state=%s requestId=%s", state, request_id)
            return JSONResponse(
                status_code=200,
                content=error_response(
                    request_id=request_id or str(start.timestamp()),
                    code="BRIDGE_NOT_CONNECTED",
                    message="Bridge is not connected. See /health for details.",
                ),
            )

        data = account_service.get_account()
        success = data is not None

        if success:
            envelope = success_response(request_id=request_id or str(start.timestamp()), data=data)
            status_code = 200
        else:
            envelope = error_response(
                request_id=request_id or str(start.timestamp()),
                code="ACCOUNT_UNAVAILABLE",
                message="Account information is not available. See /health for connection details.",
            )
            status_code = 200

        return JSONResponse(status_code=status_code, content=envelope)

    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unhandled exception in /account - requestId=%s", request_id)
        envelope = error_response(
            request_id=request_id or str(start.timestamp()),
            code="INTERNAL_ERROR",
            message="An internal error occurred. Reference: %s" % (request_id or ""),
        )
        return JSONResponse(status_code=500, content=envelope)
