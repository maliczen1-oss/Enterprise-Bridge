"""
Shared Pydantic models used across the WealthBuilder Bridge API.

Keep this module lean: only models that are genuinely reused by more than one
layer belong here.  Endpoint-specific payloads live in their respective
service or API module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Error envelope
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    """Machine-readable error payload embedded in every error response."""

    code: str = Field(..., description="Upper-snake-case error code.")
    message: str = Field(..., description="Human-readable error description.")


# ---------------------------------------------------------------------------
# Standard response envelope
# ---------------------------------------------------------------------------


class BridgeResponse(BaseModel):
    """
    Single, canonical response wrapper returned by every endpoint.

    ``data`` holds the successful payload; ``error`` holds the failure detail.
    Exactly one of the two will be non-null for any given response.
    """

    success: bool = Field(..., description="True when the operation succeeded.")
    request_id: str = Field(
        ..., alias="requestId", description="Unique identifier for this request."
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc),
        description="UTC timestamp at which the response was produced.",
    )
    data: Any | None = Field(default=None, description="Response payload on success.")
    error: ErrorDetail | None = Field(
        default=None, description="Error detail on failure."
    )

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Health payload
# ---------------------------------------------------------------------------


class HealthData(BaseModel):
    """Payload returned by GET /health."""

    application_name: str = Field(..., alias="applicationName")
    application_version: str = Field(..., alias="applicationVersion")
    api_version: str = Field(..., alias="apiVersion")
    environment: str
    startup_time: datetime = Field(..., alias="startupTime")
    uptime_seconds: float = Field(..., alias="uptimeSeconds")
    bridge_status: str = Field(..., alias="bridgeStatus")

    model_config = {"populate_by_name": True}
