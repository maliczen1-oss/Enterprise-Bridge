# tests/test_history_pagination.py
import pytest
import datetime
from httpx import AsyncClient

from bridge.app import app


@pytest.mark.asyncio
async def test_history_invalid_iso_dates(mock_manager_connected):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/api/history?start=not-a-date&end=also-bad")
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "INVALID_DATE"


@pytest.mark.asyncio
async def test_history_start_after_end(mock_manager_connected):
    now = datetime.datetime.now(datetime.timezone.utc)
    start = (now + datetime.timedelta(days=1)).isoformat()
    end = now.isoformat()
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get(f"/api/history?start={start}&end={end}")
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "INVALID_DATE_RANGE"


@pytest.mark.asyncio
async def test_history_range_too_large(mock_manager_connected):
    now = datetime.datetime.now(datetime.timezone.utc)
    start = (now - datetime.timedelta(days=365)).isoformat()
    end = now.isoformat()
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get(f"/api/history?start={start}&end={end}")
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "RANGE_TOO_LARGE"


@pytest.mark.asyncio
async def test_history_limit_exceeded(mock_manager_connected):
    now = datetime.datetime.now(datetime.timezone.utc)
    start = (now - datetime.timedelta(days=1)).isoformat()
    end = now.isoformat()
    # Use an excessively large limit to trigger LIMIT_EXCEEDED
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get(f"/api/history?start={start}&end={end}&limit=1000000")
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "LIMIT_EXCEEDED"
