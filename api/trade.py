"""
ATLAS CERTIFICATION HEADER
name=api/trade.py
Version: 3.4.1
Change Log:
- Rebuilt the trade router from the Phase 3.3 API contract.
- Preserved POST /api/trade/open.
- Preserved PUT /api/trade/{ticket}/modify.
- Preserved DELETE /api/trade/{ticket}/close.
- Integrated with TradeService, core exceptions, canonical responses,
  request-context IDs, and ConnectionManager.
- Added defensive validation for finite numeric values and safe ticket handling.
- Added standardized handling for known bridge exceptions.
- Added safe handling for unexpected exceptions without traceback leakage.
- Preserved Phase 3.3 read-only behaviour.
- No trading execution logic is implemented in the API layer.

Production Certification: Phase 3.4.1
"""

from __future__ import annotations

import logging
import math
import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from config import settings
from core import models
from core.connection_manager import manager as connection_manager
from core.exceptions import BridgeBaseException
from core.request_context import get_request_id
from core.responses import error_response, success_response
from services import trade_service


logger = logging.getLogger("bridge")


router = APIRouter(
    prefix="/trade",
    tags=["Trade"],
)


# ============================================================================
# REQUEST MODELS
# ============================================================================


def _finite_number(
    value: float | None,
    field_name: str,
) -> float | None:
    """
    Reject NaN and infinity while preserving None.
    """
    if value is None:
        return None

    if not math.isfinite(value):
        raise ValueError(
            f"{field_name} must be a finite number"
        )

    return value


class OpenTradeRequest(BaseModel):
    """
    Request model for POST /api/trade/open.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    symbol: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Broker trading symbol.",
    )

    type: str = Field(
        ...,
        description="Trade direction: BUY or SELL.",
    )

    volume: float = Field(
        ...,
        gt=0,
        description="Trade volume in lots.",
    )

    price: Optional[float] = Field(
        default=None,
        description="Optional price for pending orders.",
    )

    stopLoss: Optional[float] = Field(
        default=None
    )

    takeProfit: Optional[float] = Field(
        default=None
    )

    expiration: Optional[datetime] = Field(
        default=None,
        description="Optional ISO-8601 expiration timestamp.",
    )

    deviation: Optional[float] = Field(
        default=0.0,
        ge=0.0,
    )

    comment: Optional[str] = Field(
        default=None,
        max_length=32,
    )

    @field_validator("symbol")
    @classmethod
    def validate_symbol(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "symbol must not be empty"
            )

        return value

    @field_validator("type")
    @classmethod
    def validate_type(
        cls,
        value: str,
    ) -> str:
        value = value.strip().upper()

        if value not in {"BUY", "SELL"}:
            raise ValueError(
                "type must be BUY or SELL"
            )

        return value

    @field_validator("volume")
    @classmethod
    def validate_volume(
        cls,
        value: float,
    ) -> float:
        result = _finite_number(
            value,
            "volume",
        )

        if result is None:
            raise ValueError(
                "volume is required"
            )

        return result

    @field_validator("price")
    @classmethod
    def validate_price(
        cls,
        value: float | None,
    ) -> float | None:
        value = _finite_number(
            value,
            "price",
        )

        if value is not None and value <= 0:
            raise ValueError(
                "price must be greater than zero"
            )

        return value

    @field_validator("stopLoss")
    @classmethod
    def validate_stop_loss(
        cls,
        value: float | None,
    ) -> float | None:
        return _finite_number(
            value,
            "stopLoss",
        )

    @field_validator("takeProfit")
    @classmethod
    def validate_take_profit(
        cls,
        value: float | None,
    ) -> float | None:
        return _finite_number(
            value,
            "takeProfit",
        )

    @field_validator("deviation")
    @classmethod
    def validate_deviation(
        cls,
        value: float | None,
    ) -> float | None:
        return _finite_number(
            value,
            "deviation",
        )

    @model_validator(mode="after")
    def validate_expiration(
        self,
    ) -> "OpenTradeRequest":
        if (
            self.expiration is not None
            and self.expiration.tzinfo is None
        ):
            raise ValueError(
                "expiration must include a timezone offset"
            )

        return self


class ModifyTradeRequest(BaseModel):
    """
    Request model for PUT /api/trade/{ticket}/modify.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    stopLoss: Optional[float] = None

    takeProfit: Optional[float] = None

    @field_validator("stopLoss")
    @classmethod
    def validate_stop_loss(
        cls,
        value: float | None,
    ) -> float | None:
        return _finite_number(
            value,
            "stopLoss",
        )

    @field_validator("takeProfit")
    @classmethod
    def validate_take_profit(
        cls,
        value: float | None,
    ) -> float | None:
        return _finite_number(
            value,
            "takeProfit",
        )

    @model_validator(mode="after")
    def validate_values(
        self,
    ) -> "ModifyTradeRequest":
        if (
            self.stopLoss is None
            and self.takeProfit is None
        ):
            raise ValueError(
                "At least one of stopLoss or takeProfit must be supplied."
            )

        return self


# ============================================================================
# HELPERS
# ============================================================================


def _request_id(
    request: Request,
) -> str:
    """
    Return the request ID established by middleware.

    Falls back to the incoming X-Request-Id header and finally
    generates a UUID when neither is available.
    """
    return (
        get_request_id()
        or request.headers.get("X-Request-Id")
        or str(uuid.uuid4())
    )


def _trading_enabled() -> bool:
    """
    Determine whether trading is enabled.

    Configuration priority:

    1. settings.BROKER_TRADING_ENABLED
    2. BROKER_TRADING_ENABLED environment variable
    3. False
    """

    try:
        configured = getattr(
            settings,
            "BROKER_TRADING_ENABLED",
            None,
        )

        if configured is not None:
            return bool(configured)

    except Exception:
        logger.debug(
            "Unable to read BROKER_TRADING_ENABLED from settings.",
            exc_info=True,
        )

    value = os.getenv(
        "BROKER_TRADING_ENABLED",
        "false",
    ).strip().lower()

    return value in {
        "1",
        "true",
        "yes",
        "on",
    }


def _json_error(
    *,
    request_id: str,
    code: str,
    message: str,
    status_code: int,
) -> JSONResponse:
    """
    Build the canonical BridgeResponse error envelope.
    """

    return JSONResponse(
        status_code=status_code,
        content=error_response(
            request_id=request_id,
            code=code,
            message=message,
        ),
    )


def _service_error(
    *,
    request_id: str,
    exc: BridgeBaseException,
) -> JSONResponse:
    """
    Convert a known bridge exception into the canonical API response.

    The exception itself controls the public error code/message/status.
    """

    return _json_error(
        request_id=request_id,
        code=exc.code,
        message=exc.message,
        status_code=int(exc.status_code),
    )


# ============================================================================
# POST /api/trade/open
# ============================================================================


@router.post(
    "/open",
    response_model=models.BridgeResponse,
    summary="Open Trade",
)
async def open_trade(
    request: Request,
    payload: OpenTradeRequest = Body(...),
) -> JSONResponse:
    """
    Open a market or pending trade.

    Trade execution remains owned by TradeService.

    Phase 3.3 TradeService intentionally raises its
    NotImplementedException for execution paths. This router therefore
    exposes the canonical HTTP 501 response without implementing trading
    logic itself.
    """

    request_id = _request_id(request)

    try:
        state = connection_manager.get_state()

        if state != "CONNECTED":
            logger.info(
                "Trade open rejected because bridge is not connected "
                "- state=%s requestId=%s",
                state,
                request_id,
            )

            return _json_error(
                request_id=request_id,
                code="BRIDGE_NOT_CONNECTED",
                message=(
                    "Bridge is not connected. "
                    "See /health for details."
                ),
                status_code=200,
            )

        if not _trading_enabled():
            logger.info(
                "Trade open rejected because trading is disabled "
                "- requestId=%s",
                request_id,
            )

            return _json_error(
                request_id=request_id,
                code="TRADING_DISABLED",
                message="Trading has been disabled.",
                status_code=403,
            )

        service = trade_service.TradeService()

        result = await service.open_trade(
            payload.model_dump()
        )

        return JSONResponse(
            status_code=200,
            content=success_response(
                request_id=request_id,
                data=result,
            ),
        )

    except BridgeBaseException as exc:
        logger.info(
            "Trade open rejected by service "
            "- code=%s requestId=%s",
            exc.code,
            request_id,
        )

        return _service_error(
            request_id=request_id,
            exc=exc,
        )

    except Exception:
        logger.exception(
            "Unhandled exception in POST /trade/open "
            "- requestId=%s",
            request_id,
        )

        return _json_error(
            request_id=request_id,
            code="INTERNAL_ERROR",
            message=(
                "An internal error occurred. "
                f"Reference: {request_id}"
            ),
            status_code=500,
        )


# ============================================================================
# PUT /api/trade/{ticket}/modify
# ============================================================================


@router.put(
    "/{ticket}/modify",
    response_model=models.BridgeResponse,
    summary="Modify Trade",
)
async def modify_trade(
    request: Request,
    ticket: int = Path(
        ...,
        ge=1,
    ),
    payload: ModifyTradeRequest = Body(...),
) -> JSONResponse:
    """
    Modify stop-loss and/or take-profit on an open position.

    Trade execution remains owned by TradeService.
    """

    request_id = _request_id(request)

    try:
        state = connection_manager.get_state()

        if state != "CONNECTED":
            logger.info(
                "Trade modify rejected because bridge is not connected "
                "- state=%s ticket=%s requestId=%s",
                state,
                ticket,
                request_id,
            )

            return _json_error(
                request_id=request_id,
                code="BRIDGE_NOT_CONNECTED",
                message=(
                    "Bridge is not connected. "
                    "See /health for details."
                ),
                status_code=200,
            )

        if not _trading_enabled():
            logger.info(
                "Trade modify rejected because trading is disabled "
                "- ticket=%s requestId=%s",
                ticket,
                request_id,
            )

            return _json_error(
                request_id=request_id,
                code="TRADING_DISABLED",
                message="Trading has been disabled.",
                status_code=403,
            )

        service = trade_service.TradeService()

        result = await service.modify_trade(
            ticket=ticket,
            stop_loss=payload.stopLoss,
            take_profit=payload.takeProfit,
        )

        return JSONResponse(
            status_code=200,
            content=success_response(
                request_id=request_id,
                data=result,
            ),
        )

    except BridgeBaseException as exc:
        logger.info(
            "Trade modify rejected by service "
            "- code=%s ticket=%s requestId=%s",
            exc.code,
            ticket,
            request_id,
        )

        return _service_error(
            request_id=request_id,
            exc=exc,
        )

    except Exception:
        logger.exception(
            "Unhandled exception in PUT /trade/%s/modify "
            "- requestId=%s",
            ticket,
            request_id,
        )

        return _json_error(
            request_id=request_id,
            code="INTERNAL_ERROR",
            message=(
                "An internal error occurred. "
                f"Reference: {request_id}"
            ),
            status_code=500,
        )


# ============================================================================
# DELETE /api/trade/{ticket}/close
# ============================================================================


@router.delete(
    "/{ticket}/close",
    response_model=models.BridgeResponse,
    summary="Close Trade",
)
async def close_trade(
    request: Request,
    ticket: int = Path(
        ...,
        ge=1,
    ),
) -> JSONResponse:
    """
    Close an open position.

    Trade execution remains owned by TradeService.
    """

    request_id = _request_id(request)

    try:
        state = connection_manager.get_state()

        if state != "CONNECTED":
            logger.info(
                "Trade close rejected because bridge is not connected "
                "- state=%s ticket=%s requestId=%s",
                state,
                ticket,
                request_id,
            )

            return _json_error(
                request_id=request_id,
                code="BRIDGE_NOT_CONNECTED",
                message=(
                    "Bridge is not connected. "
                    "See /health for details."
                ),
                status_code=200,
            )

        if not _trading_enabled():
            logger.info(
                "Trade close rejected because trading is disabled "
                "- ticket=%s requestId=%s",
                ticket,
                request_id,
            )

            return _json_error(
                request_id=request_id,
                code="TRADING_DISABLED",
                message="Trading has been disabled.",
                status_code=403,
            )

        service = trade_service.TradeService()

        result = await service.close_trade(
            ticket=ticket,
        )

        return JSONResponse(
            status_code=200,
            content=success_response(
                request_id=request_id,
                data=result,
            ),
        )

    except BridgeBaseException as exc:
        logger.info(
            "Trade close rejected by service "
            "- code=%s ticket=%s requestId=%s",
            exc.code,
            ticket,
            request_id,
        )

        return _service_error(
            request_id=request_id,
            exc=exc,
        )

    except Exception:
        logger.exception(
            "Unhandled exception in DELETE /trade/%s/close "
            "- requestId=%s",
            ticket,
            request_id,
        )

        return _json_error(
            request_id=request_id,
            code="INTERNAL_ERROR",
            message=(
                "An internal error occurred. "
                f"Reference: {request_id}"
            ),
            status_code=500,
        )
