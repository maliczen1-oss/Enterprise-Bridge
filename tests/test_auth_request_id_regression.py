from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from bridge.app import app
from api import health as health_api


@pytest.mark.asyncio
async def test_auth_rejection_always_has_a_generated_request_id():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/account")

    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "AUTHENTICATION_FAILED"
    assert isinstance(body["requestId"], str)
    assert body["requestId"]
    assert response.headers["X-Request-ID"] == body["requestId"]


@pytest.mark.asyncio
async def test_health_preserves_unsupported_platform_diagnostics(monkeypatch):
    monkeypatch.setattr(
        health_api.connection_manager,
        "get_health",
        lambda: {"connectionState": "UNSUPPORTED_PLATFORM", "mt5Initialized": False},
    )
    monkeypatch.setattr(
        health_api.connection_manager,
        "get_capabilities",
        lambda: {"state": "UNSUPPORTED_PLATFORM", "platform": "linux"},
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["data"]["connectionState"] == "UNSUPPORTED_PLATFORM"
    assert response.headers["X-Request-ID"] == body["requestId"]
