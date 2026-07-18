# api/symbols.py
from fastapi import APIRouter
from datetime import datetime, timezone
import logging

from core import models
from services import symbol_service

router = APIRouter()
logger = logging.getLogger("bridge")


@router.get("/symbols", response_model=models.BridgeResponse)
async def symbols():
    start = datetime.now(timezone.utc)
    logger.info("GET /symbols called")
    try:
        data = symbol_service.get_symbols()
        envelope = {
            "success": True,
            "requestId": None,
            "timestamp": start.isoformat(),
            "data": data,
            "error": None
        }
        return envelope
    except Exception as exc:
        logger.error("Error in symbols endpoint: %s", exc)
        envelope = {
            "success": False,
            "requestId": None,
            "timestamp": start.isoformat(),
            "data": None,
            "error": {
                "code": "SYMBOLS_ERROR",
                "message": "Unable to fetch symbols."
            }
        }
        return envelope
