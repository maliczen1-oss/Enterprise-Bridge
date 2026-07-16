"""
Health router — GET /health

The only endpoint that does not require authentication.  Returns a rich
status payload so operations teams can monitor the bridge at a glance.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from bridge.core.models import HealthData
from bridge.core.request_context import get_request_id
from bridge.core.responses import success_response

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    summary="Bridge health check",
    description=(
        "Returns the current operational status of the WealthBuilder Bridge. "
        "This endpoint is publicly accessible and does not require authentication."
    ),
    response_description="Bridge status payload.",
)
async def health_check(request: Request) -> JSONResponse:
    """Return the current health and uptime of the bridge."""
    from bridge.config import settings  # deferred to avoid circular import

    startup_time: datetime = request.app.state.startup_time
    uptime_seconds: float = time.monotonic() - request.app.state.startup_monotonic

    connection_manager = request.app.state.connection_manager
    bridge_status = connection_manager.state.value

    payload = HealthData(
        applicationName=settings.app_title,
        applicationVersion=settings.app_version,
        apiVersion=settings.api_version,
        environment=settings.environment,
        startupTime=startup_time,
        uptimeSeconds=round(uptime_seconds, 3),
        bridgeStatus=bridge_status,
    )

    return JSONResponse(
        status_code=200,
        content=success_response(
            request_id=get_request_id(),
            data=payload.model_dump(by_alias=True, mode="json"),
        ),
    )
