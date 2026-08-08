"""
ATLAS CERTIFICATION HEADER

name=api/trade.py
Version: 3.3.2

Change Log
----------
• Migrated validation for Pydantic v2 compatibility.
• Replaced deprecated root_validator usage.
• Replaced deprecated validator usage.
• Preserved complete API contract.
• Preserved Atlas response envelopes.
• No behavioural changes.

Production Certification:
Atlas Phase 3.3.2
"""

from __future__ import annotations

import logging
import os

from datetime import datetime
from datetime import timezone

from typing import Any
from typing import Optional

from fastapi import APIRouter
from fastapi import Body
from fastapi import Path
from fastapi import Request

from fastapi.responses import JSONResponse

from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

from config import settings

from core.connection_manager import manager as connection_manager
from core.exceptions import BridgeBaseException
from core.request_context import get_request_id
from core.responses import error_response
from core.responses import success_response

from services import trade_service

router = APIRouter(
    prefix="/trade",
    tags=["Trade"],
)

logger = logging.getLogger("bridge")


# ==========================================================
# Request Models
# ==========================================================


class OpenTradeRequest(BaseModel):

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
        description="Pending order price",
    )

    stopLoss: Optional[float] = None

    takeProfit: Optional[float] = None

    expiration: Optional[datetime] = Field(
        default=None,
        description="ISO-8601 UTC expiration",
    )

    deviation: Optional[float] = Field(
        default=0.0,
        ge=0,
    )

    comment: Optional[str] = Field(
        default=None,
        max_length=32,
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str):

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

    stopLoss: Optional[float] = None

    takeProfit: Optional[float] = None

    @model_validator(mode="after")
    def validate_request(self):

        if (
            self.stopLoss is None
            and self.takeProfit is None
        ):
            raise ValueError(
                "At least one of stopLoss or takeProfit must be supplied."
            )

        return self


# ==========================================================
# Helpers
# ==========================================================


def trading_enabled() -> bool:
    """
    Determines whether broker trading is enabled.

    Priority

    1. config.settings

    2. Environment variable

    3. Disabled
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
            "Unable to read BROKER_TRADING_ENABLED from settings."
        )

    return (
        os.getenv(
            "BROKER_TRADING_ENABLED",
            "false",
        ).lower()
        in (
            "1",
            "true",
            "yes",
        )
    )


def bridge_connected() -> bool:

    return (
        connection_manager.get_state()
        == "CONNECTED"
    )
