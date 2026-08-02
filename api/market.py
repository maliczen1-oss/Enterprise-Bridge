"""
ATLAS CERTIFICATION HEADER
name=api/market.py
Version: 3.2.0
Change Log:
- Productionized market endpoint: canonical BridgeResponse envelope, requestId propagation,
  input validation, connection checks, and defensive error handling to avoid raw exceptions.
- Returns MARKET_UNAVAILABLE when data is missing and uses standardized error envelopes.

Production Certification: Phase 3.2
"""

# api/market.py
from fastapi import APIRouter, Path, Request
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
import logging

from core import models
from services import market_service
from core.connection_manager import manager as connection_manager
from core.request_context import get_request_id
from core.responses import success_response, error_response

router = APIRouter()
logger = logging.getLogger("bridge")


@router.get("/market/{symbol}", response_model=models.BridgeResponse)
async def market(symbol: str = Path(..., description="Symbol to query"), request: Request = None):
    request_id = get_request_id() or (request.headers.get("X-Request-Id") if request else None) or ""
    start = datetime.now(timezone.utc)

    try:
        # Basic validation: symbol should be non-empty and reasonable length
        if not symbol or len(symbol) > 64:
            return JSONResponse(status_code=400, content=error_response(request_id=request_id or str(start.timestamp()), code="INVALID_SYMBOL", message="Symbol is invalid"))

        state = connection_manager.get_state()
        if state != "CONNECTED":
            logger.info("Market requested but bridge not connected - state=%s symbol=%s requestId=%s", state, symbol, request_id)
            return JSONResponse(status_code=200, content=error_response(request_id=request_id or str(start.timestamp()), code="BRIDGE_NOT_CONNECTED", message="Bridge is not connected. See /health for details."))

        data = market_service.get_market(symbol)
        if data is None:
            return JSONResponse(status_code=200, content=error_response(request_id=request_id or str(start.timestamp()), code="MARKET_UNAVAILABLE", message=f"Market data for symbol '{symbol}' is not available."))

        envelope = success_response(request_id=request_id or str(start.timestamp()), data=data)
        return JSONResponse(status_code=200, content=envelope)

    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unhandled exception in /market/%s - requestId=%s", symbol, request_id)
        envelope = error_response(request_id=request_id or str(start.timestamp()), code="INTERNAL_ERROR", message="An internal error occurred. Reference: %s" % (request_id or ""))
        return JSONResponse(status_code=500, content=envelope)
