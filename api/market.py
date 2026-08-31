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
from fastapi import APIRouter, Path, Query, Request
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
ALLOWED_TIMEFRAMES = {"M1", "M5", "M15", "H1", "H4", "D1", "W1"}


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


@router.get("/market/{symbol}/bars", response_model=models.BridgeResponse)
async def market_bars(
    symbol: str = Path(..., description="Symbol to query"),
    timeframe: str = Query("H1", description="Allowlisted MT5 timeframe"),
    count: int = Query(500, ge=10, le=10000),
    request: Request = None,
):
    request_id = get_request_id() or (request.headers.get("X-Request-Id") if request else None) or ""
    # Broker symbol identifiers can contain case-sensitive suffixes (for
    # example, VaultMarkets exposes ``XAUUSD.mic``). Preserve the broker's
    # exact casing while still trimming surrounding whitespace.
    normalized_symbol = symbol.strip() if isinstance(symbol, str) else ""
    normalized_timeframe = timeframe.strip().upper() if isinstance(timeframe, str) else ""

    if not normalized_symbol or len(normalized_symbol) > 64:
        return JSONResponse(status_code=400, content=error_response(request_id=request_id, code="INVALID_SYMBOL", message="Symbol is invalid."))
    if normalized_timeframe not in ALLOWED_TIMEFRAMES:
        return JSONResponse(status_code=400, content=error_response(request_id=request_id, code="INVALID_TIMEFRAME", message="Timeframe is not supported."))
    if connection_manager.get_state() != "CONNECTED":
        return JSONResponse(status_code=503, content=error_response(request_id=request_id, code="BRIDGE_NOT_CONNECTED", message="Bridge is not connected. See /health for details."))

    try:
        data = market_service.get_bars(normalized_symbol, normalized_timeframe, count)
        if not data["bars"]:
            return JSONResponse(status_code=200, content=error_response(request_id=request_id, code="MARKET_BARS_UNAVAILABLE", message="Verified OHLC bars are unavailable for this request."))
        return JSONResponse(status_code=200, content=success_response(request_id=request_id, data=data))
    except Exception:
        logger.exception("Unhandled exception in market bars endpoint - requestId=%s", request_id)
        return JSONResponse(status_code=500, content=error_response(request_id=request_id, code="INTERNAL_ERROR", message="Unable to fetch verified market bars."))
