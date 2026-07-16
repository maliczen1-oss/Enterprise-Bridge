"""
Account router.

All endpoints return HTTP 501 in Phase 2.1.  Broker account retrieval is
implemented in Phase 2.2.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from bridge.core.request_context import get_request_id
from bridge.core.responses import not_implemented_response

router = APIRouter(prefix="/account", tags=["Account"])


@router.get(
    "",
    summary="Retrieve account information",
    description="Returns broker account details. Implemented in Phase 2.2.",
)
async def get_account(request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_response(request_id=get_request_id()),
    )


@router.get(
    "/balance",
    summary="Retrieve account balance",
    description="Returns the current account balance and equity. Implemented in Phase 2.2.",
)
async def get_balance(request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_response(request_id=get_request_id()),
    )


@router.get(
    "/margin",
    summary="Retrieve margin information",
    description="Returns used margin, free margin, and margin level. Implemented in Phase 2.2.",
)
async def get_margin(request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=not_implemented_response(request_id=get_request_id()),
    )
