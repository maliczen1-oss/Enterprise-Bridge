"""
ATLAS CERTIFICATION HEADER
name=api/trade.py
Version: 3.3.1
Change Log:
- Hardened trading availability gate to reuse existing configuration system when available.
- trading_enabled() now checks config.settings for BROKER_TRADING_ENABLED before falling back to environment variable.
- Documented new configuration option only if no existing mechanism is present.
- Preserves previous validation, canonical envelopes, and defensive error handling.

Production Certification: Phase 3.3
"""

# api/trade.py
from __future__ import annotations

from fastapi import APIRouter, Request, Path, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, root_validator, validator
from typing import Any, Optional
from datetime import datetime, timezone
import logging
import os

from core.request_context import get_request_id
from core.responses import success_response, error_response
from core.connection_manager import manager as connection_manager
from services import trade_service
from core.exceptions import BridgeBaseException

# Prefer using the project's configuration system if available
from config import settings

router = APIRouter(prefix="/trade", tags=["Trade"])
logger = logging.getLogger("bridge")


class OpenTradeRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=64)
    type: str = Field(..., description="BUY or SELL")
    volume: float = Field(..., gt=0, description="Volume in lots")
    price: Optional[float] = Field(None, description="Price for pending orders; null for market")
    stopLoss: Optional[float] = Field(None)
    takeProfit: Optional[float] = Field(None)
    expiration: Optional[datetime] = Field(None, description="ISO-8601 UTC expiry for pending orders")
    deviation: Optional[float] = Field(0.0, ge=0.0)
    comment: Optional[str] = Field(None, max_length=32)

    @validator("type")
    def check_type(cls, v: str) -> str:
        up = v.upper()
        if up not in ("BUY", "SELL"):
            raise ValueError("type must be 'BUY' or 'SELL'")
        return up

    @root_validator
    def validate_price_for_pending(cls, values: dict[str, Any]) -> dict[str, Any]:
        price = values.get("price")
        # If price is provided we assume it's a pending order; ensure price > 0
        if price is not None and price <= 0:
            raise ValueError("price must be > 0 for pending orders")
        return values


class ModifyTradeRequest(BaseModel):
    stopLoss: Optional[float] = Field(None)
    takeProfit: Optional[float] = Field(None)

    @root_validator
    def at_least_one(cls, values: dict[str, Any]) -> dict[str, Any]:
        if values.get("stopLoss") is None and values.get("takeProfit") is None:
            raise ValueError("At least one of stopLoss or takeProfit must be provided")
        return values


# Utility: determine trading availability (reuse config if present)
def trading_enabled() -> bool:
    """
    Determine whether trading is permitted on this instance.

    Priority:
    1. Use `settings.BROKER_TRADING_ENABLED` if present in the project's configuration.
    2. Otherwise fall back to environment variable `BROKER_TRADING_ENABLED`.

    Note: We do NOT introduce a new required configuration variable silently. If
    `BROKER_TRADING_ENABLED` is not present in settings, the environment variable
    is used. If you want this exposed in the project's Settings, add:

        BROKER_TRADING_ENABLED: bool = Field(False, env="BROKER_TRADING_ENABLED")

    to config.Settings and document it in .env.example.
    """
    # 1) Try project settings
    try:
        cfg_val = getattr(settings, "BROKER_TRADING_ENABLED", None)
        if cfg_val is not None:
            return bool(cfg_val)
    except Exception:
        # Be defensive: if settings is not present or raises, fall back to env
        logger.debug("settings.BROKER_TRADING_ENABLED unavailable, falling back to env")

    # 2) Fallback to environment variable (safe default: disabled)
    val = os.environ.get("BROKER_TRADING_ENABLED", "false").lower()
    return val in ("1", "true", "yes")


@router.post("/open", summary="Open a new trade", description="Validate and (Phase 2.2+) open a new trade")
async def open_trade(request: Request, payload: OpenTradeRequest = Body(...)):
    request_id = get_request_id() or request.headers.get("X-Request-Id") or ""
    start_ts = datetime.now(timezone.utc)

    try:
        # Basic connection and trading availability checks
        state = connection_manager.get_state()
        if state != "CONNECTED":
            logger.info("Open trade requested but bridge not connected - requestId=%s", request_id)
            return JSONResponse(
                status_code=200,
                content=error_response(
                    request_id=request_id or str(start_ts.timestamp()),
                    code="BRIDGE_NOT_CONNECTED",
                    message="Bridge is not connected. See /health for details.",
                ),
            )

        if not trading_enabled():
            logger.info("Trading disabled - requestId=%s", request_id)
            return JSONResponse(
                status_code=403,
                content=error_response(
                    request_id=request_id or str(start_ts.timestamp()),
                    code="TRADING_DISABLED",
                    message="Trading is currently disabled on this bridge instance.",
                ),
            )

        # At this stage validation already performed by Pydantic (payload). Do not execute the trade.
        # If service is present and implements open_trade, call it; otherwise return NOT_IMPLEMENTED.
        try:
            result = await trade_service.TradeService().open_trade(payload.dict())
        except BridgeBaseException as be:
            # Map known BridgeBaseException subclasses to canonical BridgeResponse envelopes
            logger.info("Trade operation not implemented or refused - %s requestId=%s", be.code, request_id)
            return JSONResponse(
                status_code=int(be.status_code),
                content=error_response(
                    request_id=request_id or str(start_ts.timestamp()),
                    code=be.code,
                    message=be.message,
                ),
            )
        except Exception:
            # Defensive: never leak internal broker/MT5 exceptions
            logger.exception("Error executing open trade - requestId=%s", request_id)
            return JSONResponse(
                status_code=503,
                content=error_response(
                    request_id=request_id or str(start_ts.timestamp()),
                    code="BROKER_UNAVAILABLE",
                    message="Broker is unavailable or trade execution failed. See /health for details.",
                ),
            )

        envelope = success_response(request_id=request_id or str(start_ts.timestamp()), data=result)
        return JSONResponse(status_code=200, content=envelope)

    except ValueError as ve:
        # Pydantic validation errors should be handled earlier by FastAPI, but be defensive.
        return JSONResponse(
            status_code=400,
            content=error_response(
                request_id=request_id or str(start_ts.timestamp()),
                code="VALIDATION_ERROR",
                message=str(ve),
            ),
        )
    except Exception:
        logger.exception("Unhandled exception in open_trade - requestId=%s", request_id)
        return JSONResponse(
            status_code=500,
            content=error_response(
                request_id=request_id or str(start_ts.timestamp()),
                code="INTERNAL_ERROR",
                message="An internal error occurred. Reference: %s" % (request_id or ""),
            ),
        )


@router.put("/{ticket}/modify", summary="Modify an existing trade", description="Validate and modify stop-loss/take-profit")
async def modify_trade(ticket: int = Path(..., description="Broker ticket"), request: Request = None, payload: ModifyTradeRequest = Body(...)):
    request_id = get_request_id() or (request.headers.get("X-Request-Id") if request else "") or ""
    start_ts = datetime.now(timezone.utc)

    try:
        state = connection_manager.get_state()
        if state != "CONNECTED":
            logger.info("Modify trade requested but bridge not connected - requestId=%s", request_id)
            return JSONResponse(
                status_code=200,
                content=error_response(
                    request_id=request_id or str(start_ts.timestamp()),
                    code="BRIDGE_NOT_CONNECTED",
                    message="Bridge is not connected. See /health for details.",
                ),
            )

        if not trading_enabled():
            logger.info("Trading disabled - requestId=%s", request_id)
            return JSONResponse(
                status_code=403,
                content=error_response(
                    request_id=request_id or str(start_ts.timestamp()),
                    code="TRADING_DISABLED",
                    message="Trading is currently disabled on this bridge instance.",
                ),
            )

        # Call service
        try:
            result = await trade_service.TradeService().modify_trade(ticket=ticket, stop_loss=payload.stopLoss, take_profit=payload.takeProfit)
        except BridgeBaseException as be:
            logger.info("Trade operation not implemented or refused - %s requestId=%s", be.code, request_id)
            return JSONResponse(
                status_code=int(be.status_code),
                content=error_response(
                    request_id=request_id or str(start_ts.timestamp()),
                    code=be.code,
                    message=be.message,
                ),
            )
        except Exception:
            logger.exception("Error modifying trade - requestId=%s ticket=%s", request_id, ticket)
            return JSONResponse(
                status_code=503,
                content=error_response(
                    request_id=request_id or str(start_ts.timestamp()),
                    code="BROKER_UNAVAILABLE",
                    message="Broker is unavailable or modification failed. See /health for details.",
                ),
            )

        envelope = success_response(request_id=request_id or str(start_ts.timestamp()), data=result)
        return JSONResponse(status_code=200, content=envelope)

    except ValueError as ve:
        return JSONResponse(
            status_code=400,
            content=error_response(
                request_id=request_id or str(start_ts.timestamp()),
                code="VALIDATION_ERROR",
                message=str(ve),
            ),
        )
    except Exception:
        logger.exception("Unhandled exception in modify_trade - requestId=%s", request_id)
        return JSONResponse(
            status_code=500,
            content=error_response(
                request_id=request_id or str(start_ts.timestamp()),
                code="INTERNAL_ERROR",
                message="An internal error occurred. Reference: %s" % (request_id or ""),
            ),
        )


@router.delete("/{ticket}/close", summary="Close an open position", description="Validate and close an open position")
async def close_trade(ticket: int = Path(..., description="Broker ticket"), request: Request = None):
    request_id = get_request_id() or (request.headers.get("X-Request-Id") if request else "") or ""
    start_ts = datetime.now(timezone.utc)

    try:
        state = connection_manager.get_state()
        if state != "CONNECTED":
            logger.info("Close trade requested but bridge not connected - requestId=%s", request_id)
            return JSONResponse(
                status_code=200,
                content=error_response(
                    request_id=request_id or str(start_ts.timestamp()),
                    code="BRIDGE_NOT_CONNECTED",
                    message="Bridge is not connected. See /health for details.",
                ),
            )

        if not trading_enabled():
            logger.info("Trading disabled - requestId=%s", request_id)
            return JSONResponse(
                status_code=403,
                content=error_response(
                    request_id=request_id or str(start_ts.timestamp()),
                    code="TRADING_DISABLED",
                    message="Trading is currently disabled on this bridge instance.",
                ),
            )

        try:
            result = await trade_service.TradeService().close_trade(ticket=ticket)
        except BridgeBaseException as be:
            logger.info("Trade operation not implemented or refused - %s requestId=%s", be.code, request_id)
            return JSONResponse(
                status_code=int(be.status_code),
                content=error_response(
                    request_id=request_id or str(start_ts.timestamp()),
                    code=be.code,
                    message=be.message,
                ),
            )
        except Exception:
            logger.exception("Error closing trade - requestId=%s ticket=%s", request_id, ticket)
            return JSONResponse(
                status_code=503,
                content=error_response(
                    request_id=request_id or str(start_ts.timestamp()),
                    code="BROKER_UNAVAILABLE",
                    message="Broker is unavailable or close failed. See /health for details.",
                ),
            )

        envelope = success_response(request_id=request_id or str(start_ts.timestamp()), data=result)
        return JSONResponse(status_code=200, content=envelope)

    except ValueError as ve:
        return JSONResponse(
            status_code=400,
            content=error_response(
                request_id=request_id or str(start_ts.timestamp()),
                code="VALIDATION_ERROR",
                message=str(ve),
            ),
        )
    except Exception:
        logger.exception("Unhandled exception in close_trade - requestId=%s", request_id)
        return JSONResponse(
            status_code=500,
            content=error_response(
                request_id=request_id or str(start_ts.timestamp()),
                code="INTERNAL_ERROR",
                message="An internal error occurred. Reference: %s" % (request_id or ""),
            ),
        )
