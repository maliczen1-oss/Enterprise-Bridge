"""
Trade execution router.

All endpoints return HTTP 501 in Phase 2.1.  Order execution and management
are implemented in Phase 2.2 and later.

Note: This router is intentionally read-only at the route-definition level.
Mutation endpoints (open, modify, close) are declared so that the OpenAPI
schema is complete for client SDK generation, but no order is placed.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.request_context import get_request_id
from core.responses import not_implemented_response

router = APIRouter(prefix="/trade", tags=["Trade"])


@router.post(
    "/open",
    summary="Open a new trade",
    description="Sends a market or pending order to the broker. Implemented in Phase 2.2.",
)
async def open_trade(request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_response(request_id=get_request_id()),
    )


@router.put(
    "/{ticket}/modify",
    summary="Modify an existing trade",
    description="Modifies stop-loss or take-profit for an open position. Implemented in Phase 2.2.",
)
async def modify_trade(ticket: int, request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_response(request_id=get_request_id()),
    )


@router.delete(
    "/{ticket}/close",
    summary="Close an open position",
    description="Sends a close order for an open position by ticket. Implemented in Phase 2.2.",
)
async def close_trade(ticket: int, request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_response(request_id=get_request_id()),
    )
