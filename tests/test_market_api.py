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


@pytest.mark.asyncio
async def test_market_bars_success(client, mock_manager_connected, monkeypatch):
    monkeypatch.setattr(
        "api.market.market_service.get_bars",
        lambda symbol, timeframe, count: {
            "schemaVersion": "1.0",
            "symbol": symbol,
            "timeframe": timeframe,
            "priceBasis": "BID",
            "source": "LOCAL_MT5",
            "barCount": 1,
            "bars": [{"time": 1, "open": 1, "high": 2, "low": 0.5, "close": 1.5}],
        },
    )
    response = await client.get(
        "/api/market/XAUUSD/bars?timeframe=H4&count=100",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["timeframe"] == "H4"


@pytest.mark.asyncio
async def test_market_bars_rejects_unknown_timeframe(client, mock_manager_connected):
    response = await client.get(
        "/api/market/XAUUSD/bars?timeframe=H2&count=100",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_TIMEFRAME"
