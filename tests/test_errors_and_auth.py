# tests/test_errors_and_auth.py
import pytest
from httpx import AsyncClient

from bridge.app import app
from config import settings

AUTH_HEADER = {"Authorization": "Bearer test-token"}


@pytest.mark.asyncio
async def test_protected_endpoints_require_auth(mock_manager_connected):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # account
        r = await ac.get("/api/account")
        assert r.status_code == 401

        # positions
        r = await ac.get("/api/positions")
        assert r.status_code == 401

        # symbols
        r = await ac.get("/api/symbols")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_endpoints_return_structured_errors_when_bridge_unavailable(mock_manager_disconnected):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # account
        r = await ac.get("/api/account", headers=AUTH_HEADER)
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is False
        assert body["error"] is not None

        # positions
        r = await ac.get("/api/positions", headers=AUTH_HEADER)
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is False or isinstance(body["data"], list)

        # symbols
        r = await ac.get("/api/symbols", headers=AUTH_HEADER)
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is False or isinstance(body["data"], list)
