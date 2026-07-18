# api/account.py
from fastapi import APIRouter, Depends
from datetime import datetime, timezone
import logging

from core import models
from services import account_service
from core.connection_manager import manager as connection_manager

router = APIRouter()
logger = logging.getLogger("bridge")


@router.get("/account", response_model=models.BridgeResponse)
async def account():
    start = time_now = datetime.now(timezone.utc)
    logger.info("GET /account called")
    data = account_service.get_account()
    success = data is not None
    envelope = {
        "success": success,
        "requestId": None,
        "timestamp": time_now.isoformat(),
        "data": data if success else None,
        "error": None if success else {
            "code": "ACCOUNT_UNAVAILABLE",
            "message": "Account information is not available. See health for connection details."
        }
    }
    if not success:
        envelope["data"] = None
    return envelope
