"""
Market data router.

All endpoints return HTTP 501 in Phase 2.1.  Live market data retrieval is
implemented in Phase 2.2.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from bridge.core.request_context import get_request_id
from bridge.core.responses import not_implemented_response

router = APIRouter(prefix="/market", tags=["Market"])


@router.get(
    "/{symbol}/tick",
    summary="Retrieve latest tick for a symbol",
    description="Returns the most recent bid/ask tick for a trading symbol. Implemented in Phase 2.2.",
)
async def get_tick(symbol: str, request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_response(request_id=get_request_id()),
    )


@router.get(
    "/{symbol}/rates",
    summary="Retrieve historical OHLCV rates",
    description="Returns OHLCV candlestick data for a symbol and timeframe. Implemented in Phase 2.2.",
)
async def get_rates(symbol: str, request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_response(request_id=get_request_id()),
    )
