# tests/test_history_api.py
from __future__ import annotations

import pytest
from datetime import datetime, timedelta


@pytest.mark.asyncio
async def test_history_invalid_dates(client, mock_manager_connected):
    resp = await client.get("/history?start=notadate&end=alsonot", headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 400
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_DATE"


@pytest.mark.asyncio
async def test_history_success(client, mock_manager_connected):
    now = datetime.utcnow()
    start = (now - timedelta(days=1)).isoformat()
    end = now.isoformat()
    resp = await client.get(f"/history?start={start}&end={end}", headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)
