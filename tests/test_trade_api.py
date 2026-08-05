# tests/test_trade_api.py
from __future__ import annotations

import os
import pytest
from httpx import AsyncClient

from services import trade_service
from core.exceptions import NotImplementedException


@pytest.mark.asyncio
async def test_open_trade_bridge_not_connected(client: AsyncClient, mock_manager_disconnected):
    # Bridge disconnected -> BRIDGE_NOT_CONNECTED error envelope
    os.environ.pop("BROKER_TRADING_ENABLED", None)
    resp = await client.post("/trade/open", json={
        "symbol": "EURUSD",
        "type": "BUY",
        "volume": 0.1,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "BRIDGE_NOT_CONNECTED"


@pytest.mark.asyncio
async def test_open_trade_trading_disabled(client: AsyncClient, mock_manager_connected, monkeypatch):
    # Trading disabled via settings
    monkeypatch.setattr("config.settings", "BROKER_TRADING_ENABLED", False, raising=False)
    resp = await client.post("/trade/open", json={
        "symbol": "EURUSD",
        "type": "BUY",
        "volume": 0.1,
    })
    assert resp.status_code == 403
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "TRADING_DISABLED"


@pytest.mark.asyncio
async def test_open_trade_not_implemented(client: AsyncClient, mock_manager_connected, monkeypatch):
    # Ensure TradeService raises NotImplementedException and maps to 501
    async def _open(payload):
        raise NotImplementedException("disabled")

    monkeypatch.setattr(trade_service.TradeService, "open_trade", _open)

    # Enable trading so the request reaches the service layer
    monkeypatch.setattr("config.settings", "BROKER_TRADING_ENABLED", True, raising=False)

    resp = await client.post("/trade/open", json={
        "symbol": "EURUSD",
        "type": "BUY",
        "volume": 0.1,
    })
    assert resp.status_code == 501
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_IMPLEMENTED"


@pytest.mark.asyncio
async def test_open_trade_success(client: AsyncClient, mock_manager_connected, monkeypatch):
    # Simulate a successful trade response from the service
    async def _open(payload):
        return {"ticket": 1234, "price": 1.1010}

    monkeypatch.setattr(trade_service.TradeService, "open_trade", _open)
    monkeypatch.setattr("config.settings", "BROKER_TRADING_ENABLED", True, raising=False)

    resp = await client.post("/trade/open", json={
        "symbol": "EURUSD",
        "type": "BUY",
        "volume": 0.1,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["ticket"] == 1234
