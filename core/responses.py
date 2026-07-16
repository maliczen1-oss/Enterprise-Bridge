"""
Response builder helpers.

Centralises the construction of BridgeResponse objects so route handlers
never assemble the envelope manually.  Every helper returns a dict suitable
for direct use with ``JSONResponse`` or ``fastapi.responses.JSONResponse``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bridge.core.models import BridgeResponse, ErrorDetail


def success_response(*, request_id: str, data: Any) -> dict[str, Any]:
    """Build a serialisable success envelope."""
    envelope = BridgeResponse(
        success=True,
        requestId=request_id,
        timestamp=datetime.now(tz=timezone.utc),
        data=data,
        error=None,
    )
    return envelope.model_dump(by_alias=True, mode="json")


def error_response(
    *,
    request_id: str,
    code: str,
    message: str,
) -> dict[str, Any]:
    """Build a serialisable error envelope."""
    envelope = BridgeResponse(
        success=False,
        requestId=request_id,
        timestamp=datetime.now(tz=timezone.utc),
        data=None,
        error=ErrorDetail(code=code, message=message),
    )
    return envelope.model_dump(by_alias=True, mode="json")


def not_implemented_response(*, request_id: str) -> dict[str, Any]:
    """Build the canonical HTTP 501 envelope for stub endpoints."""
    return error_response(
        request_id=request_id,
        code="NOT_IMPLEMENTED",
        message="This endpoint will be implemented in a future phase.",
    )
