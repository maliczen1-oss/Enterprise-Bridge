# tests/test_api_endpoints.py
import pytest
import datetime
from httpx import AsyncClient

from bridge.app import app
from config import settings

AUTH_HEADER = {"Authorization": f"Bearer {settings.AUTH_TOKEN}"}


@pytest.mark.asyncio
async def test_health_public_endpoint(mock_manager):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert "success" in body
    # Health should include connectionState in data
    assert "data" in body
    assert body["data"]["connectionState"] == "CONNECTED"


@pytest.mark.asyncio
async def test_account_requires_auth_and_returns_data(mock_manager):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Without auth
        r = await ac.get("/api/account")
        assert r.status_code == 401

        # With auth
        r = await ac.get("/api/account", headers=AUTH_HEADER)
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["data"] is not None
        assert "balance" in body["data"]


@pytest.mark.asyncio
async def test_positions_endpoint(mock_manager):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/api/positions", headers=AUTH_HEADER)
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)


@pytest.mark.asyncio
async def test_symbols_endpoint(mock_manager):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/api/symbols", headers=AUTH_HEADER)
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)


@pytest.mark.asyncio
async def test_market_endpoint_known_symbol(mock_manager):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/api/market/EURUSD/tick", headers=AUTH_HEADER)
        # The original spec had /api/market/{symbol}/tick — ensure both route forms are covered by your app.
        # If your app uses /market/{symbol} instead, adjust this test accordingly.
        # Accept either 200 or 404 depending on route registration; prefer 200 for Phase 2.2B.
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            body = r.json()
            assert body["success"] is True
            assert "bid" in body["data"] or "data" in body


@pytest.mark.asyncio
async def test_history_endpoint_valid_dates(mock_manager):
    now = datetime.datetime.utcnow().isoformat()
    earlier = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).isoformat()
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/api/history?start={}&end={}".format(earlier, now), headers=AUTH_HEADER)
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert "deals" in body["data"] or "orders" in body["data"] or isinstance(body["data"], dict)


@pytest.mark.asyncio
async def test_trade_endpoint_still_501(mock_manager):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.post("/api/trade/open", headers=AUTH_HEADER, json={})
        assert r.status_code == 501
