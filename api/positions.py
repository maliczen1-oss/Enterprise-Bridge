"""
Positions router.

All endpoints return HTTP 501 in Phase 2.1.  Open position retrieval is
implemented in Phase 2.2.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from bridge.core.request_context import get_request_id
from bridge.core.responses import not_implemented_response

router = APIRouter(prefix="/positions", tags=["Positions"])


@router.get(
    "",
    summary="List open positions",
    description="Returns all currently open positions. Implemented in Phase 2.2.",
)
async def list_positions(request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_response(request_id=get_request_id()),
    )


@router.get(
    "/{ticket}",
    summary="Retrieve a position by ticket",
    description="Returns a single open position by its broker ticket number. Implemented in Phase 2.2.",
)
async def get_position(ticket: int, request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_response(request_id=get_request_id()),
    )
