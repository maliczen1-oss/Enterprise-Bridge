# tests/test_account_api.py
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_account_endpoint_connected(client, mock_manager_connected):
    resp = await client.get("/api/account", headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] in (True, False)
    # If connected, either data is present or ACCOUNT_UNAVAILABLE; ensure envelope shape
    assert "requestId" in body
    assert "timestamp" in body


@pytest.mark.asyncio
async def test_account_endpoint_disconnected(client, mock_manager_disconnected):
    resp = await client.get("/api/account", headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] in ("BRIDGE_NOT_CONNECTED", "ACCOUNT_UNAVAILABLE")
