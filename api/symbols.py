"""
Symbols router.

All endpoints return HTTP 501 in Phase 2.1.  Symbol catalogue retrieval is
implemented in Phase 2.2.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from bridge.core.request_context import get_request_id
from bridge.core.responses import not_implemented_response

router = APIRouter(prefix="/symbols", tags=["Symbols"])


@router.get(
    "",
    summary="List available trading symbols",
    description="Returns all symbols available on the connected broker. Implemented in Phase 2.2.",
)
async def list_symbols(request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_response(request_id=get_request_id()),
    )


@router.get(
    "/{symbol}",
    summary="Retrieve symbol information",
    description="Returns specification details for a named trading symbol. Implemented in Phase 2.2.",
)
async def get_symbol(symbol: str, request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_response(request_id=get_request_id()),
    )
