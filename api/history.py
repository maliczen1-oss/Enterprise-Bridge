# api/history.py
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
import logging
import datetime as dt
from typing import Optional

from core import models
from services import history_service
from core.request_context import get_request_id
from core.responses import success_response, error_response

router = APIRouter()
logger = logging.getLogger("bridge")


@router.get("/history", response_model=models.BridgeResponse)
async def history(
    request: Request,
    start: str = Query(..., description="ISO8601 start datetime"),
    end: str = Query(..., description="ISO8601 end datetime"),
    ticket: Optional[int] = Query(None),
    symbol: Optional[str] = Query(None),
    limit: Optional[int] = Query(None),
):
    request_id = get_request_id() or request.headers.get("X-Request-Id") or ""
    request_time = datetime.now(timezone.utc)
    logger.info("GET /history called start=%s end=%s ticket=%s symbol=%s limit=%s requestId=%s", start, end, ticket, symbol, limit, request_id)

    try:
        try:
            from_dt = dt.datetime.fromisoformat(start)
            to_dt = dt.datetime.fromisoformat(end)
        except Exception:
            return JSONResponse(
                status_code=400,
                content=error_response(
                    request_id=request_id or request_time.isoformat(),
                    code="INVALID_DATE",
                    message="start and end must be ISO8601 datetimes",
                ),
            )

        data = history_service.get_history(from_dt, to_dt, ticket=ticket, symbol=symbol, limit=limit)
        envelope = success_response(request_id=request_id or request_time.isoformat(), data=data)
        return JSONResponse(status_code=200, content=envelope)

    except Exception as exc:
        logger.exception("Error in history endpoint - requestId=%s", request_id)
        return JSONResponse(
            status_code=500,
            content=error_response(
                request_id=request_id or request_time.isoformat(),
                code="HISTORY_ERROR",
                message="Unable to fetch history.",
            ),
        )
