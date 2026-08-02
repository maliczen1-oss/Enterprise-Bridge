"""
ATLAS CERTIFICATION HEADER
name=api/history.py
Version: 3.3.0
Change Log:
- Implemented production-ready history endpoint with strict ISO-8601 validation,
  configurable max range and max record limits, pagination (page, limit), and
  canonical BridgeResponse envelopes.
- Validates inputs and returns structured validation errors; handles bridge
  disconnected/unavailable states without raising; never exposes stack traces
  or MT5 exceptions.

Production Certification: Phase 3.3
"""

# api/history.py
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
import logging
import datetime as dt
from typing import Optional

from core import models
from core.request_context import get_request_id
from core.responses import success_response, error_response
from core.connection_manager import manager as connection_manager
from services import history_service

from config import settings

router = APIRouter()
logger = logging.getLogger("bridge")


@router.get("/history", response_model=models.BridgeResponse)
async def history(
    request: Request,
    start: str = Query(..., description="ISO8601 start datetime"),
    end: str = Query(..., description="ISO8601 end datetime"),
    ticket: Optional[int] = Query(None),
    symbol: Optional[str] = Query(None),
    page: int = Query(1, ge=1, description="Page number, 1-indexed"),
    limit: int = Query(None, ge=1, description="Records per page"),
):
    """Return historical deals/orders with pagination and strict validation.

    - start/end: ISO-8601 datetimes (required)
    - page: 1-indexed page number
    - limit: records per page (default controlled by settings)

    The endpoint never exposes raw exceptions or MT5 tracebacks.
    """
    request_id = get_request_id() or request.headers.get("X-Request-Id") or ""
    now = datetime.now(timezone.utc)

    # Configurable limits
    max_limit = int(getattr(settings, "HISTORY_MAX_LIMIT", 1000))
    default_limit = int(getattr(settings, "HISTORY_DEFAULT_LIMIT", 100))
    max_range_days = int(getattr(settings, "HISTORY_MAX_RANGE_DAYS", 30))

    try:
        # Parse datetimes strictly
        try:
            from_dt = dt.datetime.fromisoformat(start)
            to_dt = dt.datetime.fromisoformat(end)
        except Exception:
            return JSONResponse(
                status_code=400,
                content=error_response(
                    request_id=request_id or str(now.timestamp()),
                    code="INVALID_DATE",
                    message="start and end must be valid ISO-8601 datetimes",
                ),
            )

        # Normalize timezone: require timezone aware or assume UTC
        if from_dt.tzinfo is None:
            from_dt = from_dt.replace(tzinfo=timezone.utc)
        if to_dt.tzinfo is None:
            to_dt = to_dt.replace(tzinfo=timezone.utc)

        if from_dt >= to_dt:
            return JSONResponse(
                status_code=400,
                content=error_response(
                    request_id=request_id or str(now.timestamp()),
                    code="INVALID_DATE_RANGE",
                    message="start must be before end",
                ),
            )

        # Enforce maximum range
        delta = to_dt - from_dt
        if delta.total_seconds() < 0 or delta.days > max_range_days:
            return JSONResponse(
                status_code=400,
                content=error_response(
                    request_id=request_id or str(now.timestamp()),
                    code="RANGE_TOO_LARGE",
                    message=f"Requested range exceeds maximum of {max_range_days} days",
                ),
            )

        # Determine effective limit
        if limit is None:
            limit = default_limit
        if limit > max_limit:
            return JSONResponse(
                status_code=400,
                content=error_response(
                    request_id=request_id or str(now.timestamp()),
                    code="LIMIT_EXCEEDED",
                    message=f"limit must be <= {max_limit}",
                ),
            )

        # Offset for pagination (page is 1-indexed)
        offset = (page - 1) * limit

        # Connection check
        state = connection_manager.get_state()
        if state != "CONNECTED":
            logger.info("History requested but bridge not connected - state=%s requestId=%s", state, request_id)
            return JSONResponse(
                status_code=200,
                content=error_response(
                    request_id=request_id or str(now.timestamp()),
                    code="BRIDGE_NOT_CONNECTED",
                    message="Bridge is not connected. See /health for details.",
                ),
            )

        # Fetch records from service (service should handle filtering by ticket/symbol)
        try:
            # history_service.get_history(from_dt, to_dt, ticket, symbol, limit, offset)
            data_records = history_service.get_history(from_dt, to_dt, ticket=ticket, symbol=symbol, limit=limit, offset=offset)
        except NotImplementedError:
            # In cases where history is not implemented yet return 501 envelope
            return JSONResponse(status_code=501, content=error_response(request_id=request_id or str(now.timestamp()), code="NOT_IMPLEMENTED", message="History retrieval not implemented"))
        except Exception as exc:
            # Never leak internal exceptions
            logger.exception("Error fetching history - requestId=%s", request_id)
            return JSONResponse(
                status_code=200,
                content=error_response(
                    request_id=request_id or str(now.timestamp()),
                    code="HISTORY_UNAVAILABLE",
                    message="Unable to fetch history at this time. See /health for connection details.",
                ),
            )

        # Build paginated response envelope
        payload = {
            "page": page,
            "limit": limit,
            "records": data_records,
        }

        envelope = success_response(request_id=request_id or str(now.timestamp()), data=payload)
        return JSONResponse(status_code=200, content=envelope)

    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected error in /history - requestId=%s", request_id)
        return JSONResponse(
            status_code=500,
            content=error_response(
                request_id=request_id or str(now.timestamp()),
                code="INTERNAL_ERROR",
                message="An internal error occurred. Reference: %s" % (request_id or ""),
            ),
        )
