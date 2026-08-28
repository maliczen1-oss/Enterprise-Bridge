# tests/test_positions_api.py
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_positions_connected(client, mock_manager_connected):
    resp = await client.get("/api/positions", headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)


@pytest.mark.asyncio
async def test_positions_disconnected(client, mock_manager_disconnected):
    resp = await client.get("/api/positions", headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
