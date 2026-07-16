"""
Trade history router.

All endpoints return HTTP 501 in Phase 2.1.  Historical deal and order
retrieval is implemented in Phase 2.2.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from bridge.core.request_context import get_request_id
from bridge.core.responses import not_implemented_response

router = APIRouter(prefix="/history", tags=["History"])


@router.get(
    "/deals",
    summary="Retrieve historical deals",
    description="Returns closed deals within a date range. Implemented in Phase 2.2.",
)
async def get_deals(request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_response(request_id=get_request_id()),
    )


@router.get(
    "/orders",
    summary="Retrieve historical orders",
    description="Returns filled and cancelled orders within a date range. Implemented in Phase 2.2.",
)
async def get_orders(request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_response(request_id=get_request_id()),
    )
