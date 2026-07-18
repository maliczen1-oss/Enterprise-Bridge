# api/positions.py
from fastapi import APIRouter
from datetime import datetime, timezone
import logging

from core import models
from services import position_service

router = APIRouter()
logger = logging.getLogger("bridge")


@router.get("/positions", response_model=models.BridgeResponse)
async def positions():
    start = datetime.now(timezone.utc)
    logger.info("GET /positions called")
    try:
        data = position_service.get_positions()
        success = True
        envelope = {
            "success": success,
            "requestId": None,
            "timestamp": start.isoformat(),
            "data": data,
            "error": None
        }
        return envelope
    except Exception as exc:
        logger.error("Error in positions endpoint: %s", exc)
        envelope = {
            "success": False,
            "requestId": None,
            "timestamp": start.isoformat(),
            "data": None,
            "error": {
                "code": "POSITIONS_ERROR",
                "message": "Unable to fetch positions."
            }
        }
        return envelope
