# tests/test_market_api.py
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_market_connected(client, mock_manager_connected):
    resp = await client.get("/api/market/EURUSD", headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert isinstance(body["data"], dict)


@pytest.mark.asyncio
async def test_market_invalid_symbol(client, mock_manager_connected):
    resp = await client.get("/api/market/", headers={"Authorization": "Bearer test-token"})
    # FastAPI will return 404 for missing path param; ensure not 500
    assert resp.status_code in (404,)
