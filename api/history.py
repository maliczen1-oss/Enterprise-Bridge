# api/history.py
from fastapi import APIRouter, Query
from datetime import datetime, timezone
import logging
import datetime as dt

from core import models
from services import history_service

router = APIRouter()
logger = logging.getLogger("bridge")


@router.get("/history", response_model=models.BridgeResponse)
async def history(
    start: str = Query(..., description="ISO8601 start datetime"),
    end: str = Query(..., description="ISO8601 end datetime"),
    ticket: int | None = Query(None),
    symbol: str | None = Query(None),
    limit: int | None = Query(None),
):
    request_time = datetime.now(timezone.utc)
    logger.info("GET /history called start=%s end=%s ticket=%s symbol=%s limit=%s", start, end, ticket, symbol, limit)
    try:
        from_dt = dt.datetime.fromisoformat(start)
        to_dt = dt.datetime.fromisoformat(end)
    except Exception:
        envelope = {
            "success": False,
            "requestId": None,
            "timestamp": request_time.isoformat(),
            "data": None,
            "error": {
                "code": "INVALID_DATE",
                "message": "start and end must be ISO8601 datetimes"
            }
        }
        return envelope

    try:
        data = history_service.get_history(from_dt, to_dt, ticket=ticket, symbol=symbol, limit=limit)
        envelope = {
            "success": True,
            "requestId": None,
            "timestamp": request_time.isoformat(),
            "data": data,
            "error": None
        }
        return envelope
    except Exception as exc:
        logger.error("Error in history endpoint: %s", exc)
        envelope = {
            "success": False,
            "requestId": None,
            "timestamp": request_time.isoformat(),
            "data": None,
            "error": {
                "code": "HISTORY_ERROR",
                "message": "Unable to fetch history."
            }
        }
        return envelope
