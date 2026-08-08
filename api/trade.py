"""
ATLAS CERTIFICATION HEADER
name=api/trade.py
Version: 3.4.0
Change Log:
- Migrated to Pydantic v2.
- Replaced deprecated validator/root_validator usage.
- Uses model_validator and field_validator.
- Uses model_dump() instead of dict().
- Preserves existing API contract.
- No behavioural changes.

Production Certification: Phase 3.4
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Body, Path, Request
from fastapi.responses import JSONResponse

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from config import settings

from core.connection_manager import manager as connection_manager
from core.exceptions import BridgeBaseException
from core.request_context import get_request_id
from core.responses import error_response, success_response

from services import trade_service

router = APIRouter(
    prefix="/trade",
    tags=["Trade"],
)

logger = logging.getLogger("bridge")


# =====================================================================
# Request Models
# =====================================================================


class OpenTradeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(
        ...,
        min_length=1,
        max_length=64,
    )

    type: str = Field(
        ...,
        description="BUY or SELL",
    )

    volume: float = Field(
        ...,
        gt=0,
        description="Volume in lots",
    )

    price: Optional[float] = Field(
        default=None,
        description="Price for pending orders",
    )

    stopLoss: Optional[float] = None
    takeProfit: Optional[float] = None

    expiration: Optional[datetime] = Field(
        default=None,
        description="ISO8601 UTC expiry",
    )

    deviation: Optional[float] = Field(
        default=0.0,
        ge=0.0,
    )

    comment: Optional[str] = Field(
        default=None,
        max_length=32,
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        value = value.upper()

        if value not in ("BUY", "SELL"):
            raise ValueError("type must be BUY or SELL")

        return value

    @model_validator(mode="after")
    def validate_pending_price(self):

        if self.price is not None:

            if self.price <= 0:
                raise ValueError(
                    "price must be greater than zero"
                )

        return self


class ModifyTradeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stopLoss: Optional[float] = None
    takeProfit: Optional[float] = None

    @model_validator(mode="after")
    def validate_values(self):

        if (
            self.stopLoss is None
            and self.takeProfit is None
        ):
            raise ValueError(
                "At least one of stopLoss or takeProfit must be supplied."
            )

        return self


# =====================================================================
# Trading Configuration
# =====================================================================


def trading_enabled() -> bool:
    """
    Returns whether broker trading has been enabled.

    Priority:

    1. config.settings.BROKER_TRADING_ENABLED

    2. Environment variable
       BROKER_TRADING_ENABLED
    """

    try:
        cfg = getattr(
            settings,
            "BROKER_TRADING_ENABLED",
            None,
        )

        if cfg is not None:
            return bool(cfg)

    except Exception:
        logger.debug(
            "Unable to read BROKER_TRADING_ENABLED "
            "from settings."
        )

    env = os.getenv(
        "BROKER_TRADING_ENABLED",
        "false",
    ).lower()

    return env in (
        "1",
        "true",
        "yes",
    )


# =====================================================================
# OPEN TRADE
# =====================================================================


@router.post(
    "/open",
    summary="Open Trade",
)
async def open_trade(
    request: Request,
    payload: OpenTradeRequest = Body(...),
):

    request_id = (
        get_request_id()
        or request.headers.get("X-Request-Id")
        or ""
    )

    started = datetime.now(timezone.utc)

    try:

        if connection_manager.get_state() != "CONNECTED":

            return JSONResponse(
                status_code=200,
                content=error_response(
                    request_id=request_id,
                    code="BRIDGE_NOT_CONNECTED",
                    message="Bridge is not connected.",
                ),
            )

        if not trading_enabled():

            return JSONResponse(
                status_code=403,
                content=error_response(
                    request_id=request_id,
                    code="TRADING_DISABLED",
                    message="Trading has been disabled.",
                ),
            )

        try:

            result = await (
                trade_service.TradeService()
                .open_trade(
                    payload.model_dump()
                )
            )
