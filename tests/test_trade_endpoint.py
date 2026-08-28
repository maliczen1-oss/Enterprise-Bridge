# tests/test_trade_endpoint.py
import pytest
from httpx import AsyncClient

from bridge.app import app
from config import settings

AUTH_HEADER = {"Authorization": "Bearer test-token"}


@pytest.mark.asyncio
async def test_trade_open_returns_501_without_side_effects(mock_manager_connected, monkeypatch):
    monkeypatch.setattr(settings, "BROKER_TRADING_ENABLED", True, raising=False)
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.post("/api/trade/open", headers=AUTH_HEADER, json={"symbol": "EURUSD", "type": "BUY", "volume": 0.1})
        assert r.status_code == 501
        body = r.json()
        assert body["success"] is False
        assert body["error"] is not None
        assert body["error"]["code"] in ("NOT_IMPLEMENTED", "TRADE_NOT_IMPLEMENTED", "NOT_IMPLEMENTED")
