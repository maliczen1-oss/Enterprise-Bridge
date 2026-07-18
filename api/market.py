# api/market.py
from fastapi import APIRouter, Path
from datetime import datetime, timezone
import logging

from core import models
from services import market_service

router = APIRouter()
logger = logging.getLogger("bridge")


@router.get("/market/{symbol}", response_model=models.BridgeResponse)
async def market(symbol: str = Path(..., description="Symbol to query")):
    start = datetime.now(timezone.utc)
    logger.info("GET /market/%s called", symbol)
    try:
        data = market_service.get_market(symbol)
        if data is None:
            envelope = {
                "success": False,
                "requestId": None,
                "timestamp": start.isoformat(),
                "data": None,
                "error": {
                    "code": "MARKET_UNAVAILABLE",
                    "message": f"Market data for symbol '{symbol}' is not available."
                }
            }
            return envelope

        envelope = {
            "success": True,
            "requestId": None,
            "timestamp": start.isoformat(),
            "data": data,
            "error": None
        }
        return envelope
    except Exception as exc:
        logger.error("Error in market endpoint for %s: %s", symbol, exc)
        envelope = {
            "success": False,
            "requestId": None,
            "timestamp": start.isoformat(),
            "data": None,
            "error": {
                "code": "MARKET_ERROR",
                "message": "Unable to fetch market data."
            }
        }
        return envelope
