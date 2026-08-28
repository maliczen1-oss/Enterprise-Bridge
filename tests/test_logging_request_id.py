# tests/test_logging_request_id.py
import logging
import pytest
from httpx import AsyncClient

from bridge.app import app
from config import settings

AUTH_HEADER = {"Authorization": "Bearer test-token"}


@pytest.mark.asyncio
async def test_request_id_in_logs_and_response(caplog, mock_manager_connected):
    caplog.set_level(logging.INFO, logger="bridge")

    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/api/account", headers=AUTH_HEADER)

    assert r.status_code == 200
    body = r.json()
    assert "requestId" in body and isinstance(body["requestId"], str) and body["requestId"]

    # Verify that the bridge logger emitted an access log containing the request id
    found = False
    for record in caplog.records:
        msg = record.getMessage()
        if "request=" in msg and "path=" in msg:
            # The middleware logs: request=%s path=%s ...
            found = True
            break
    assert found, "Expected a bridge access log record with request id"
