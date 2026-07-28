# tests/test_health.py
import pytest
import datetime
from httpx import AsyncClient

from app import app
from config import settings


@pytest.mark.asyncio
async def test_health_endpoint_structure(mock_manager_connected):
    """Verify /health returns valid BridgeResponse with all required fields."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/health")
    
    assert r.status_code == 200
    body = r.json()
    
    # Required envelope fields
    assert "success" in body
    assert "requestId" in body
    assert "timestamp" in body
    assert "data" in body
    assert "error" in body
    
    # requestId must be non-null string
    assert isinstance(body["requestId"], str)
    assert len(body["requestId"]) > 0
    
    # timestamp must be valid ISO8601
    assert isinstance(body["timestamp"], str)
    datetime.datetime.fromisoformat(body["timestamp"])


@pytest.mark.asyncio
async def test_health_endpoint_connected(mock_manager_connected):
    """Verify /health reports READY when MT5 connected."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/health")
    
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["bridgeStatus"] == "READY"
    assert body["data"]["connectionState"] == "CONNECTED"
    assert body["data"]["mt5Initialized"] is True
    assert body["error"] is None


@pytest.mark.asyncio
async def test_health_endpoint_disconnected(mock_manager_disconnected):
    """Verify /health reports FAILED when MT5 disconnected."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/health")
    
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert body["data"]["bridgeStatus"] == "FAILED"
    assert body["data"]["connectionState"] == "FAILED"
    assert body["data"]["mt5Initialized"] is False
    assert body["error"] is not None
    assert body["error"]["code"] == "CONNECTION_NOT_READY"


@pytest.mark.asyncio
async def test_health_endpoint_unsupported_platform(mock_manager_unsupported):
    """Verify /health reports UNSUPPORTED_PLATFORM on Linux."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/health")
    
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert body["data"]["bridgeStatus"] == "UNSUPPORTED_PLATFORM"
    assert body["data"]["connectionState"] == "UNSUPPORTED_PLATFORM"
    assert body["error"] is not None


@pytest.mark.asyncio
async def test_health_endpoint_public_no_auth():
    """Verify /health is public and does not require authentication."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Request without Authorization header should still reach the handler
        r = await ac.get("/health")
    
    # Should return 200, not 401
    assert r.status_code == 200
    body = r.json()
    assert "requestId" in body
    assert isinstance(body["requestId"], str)


@pytest.mark.asyncio
async def test_health_no_secret_leakage(mock_manager_connected):
    """Verify /health does not expose AUTH_TOKEN or credentials."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/health")
    
    body = r.json()
    response_str = str(body)
    
    # AUTH_TOKEN must not appear in response
    assert settings.AUTH_TOKEN not in response_str
    # Credentials must not appear
    assert "password" not in response_str.lower() or not any(
        cred in response_str for cred in [settings.MT5_PASSWORD] if cred
    )
