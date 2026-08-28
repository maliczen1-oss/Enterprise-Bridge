"""Current runtime smoke and contract tests for the Enterprise Bridge.

These tests intentionally exercise the current Phase 3 read-only surface:

* health, documentation, and OpenAPI are public;
* protected endpoints require the configured Bearer token;
* account, positions, symbols, market, and history reads use the shared
  connected-manager fixtures and return the canonical response envelope; and
* trade mutations fail closed.  They are either rejected while trading is
  disabled or map the read-only service's explicit 501 response.

The old Phase 2.1 assumptions that every API route was a stub are deliberately
not part of this file.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from httpx import AsyncClient

from config import settings


AUTH_HEADER = {"Authorization": "Bearer test-token"}
WRONG_AUTH_HEADER = {"Authorization": "Bearer wrong-token"}


def _assert_envelope(body: dict, *, success: bool | None = None) -> None:
    """Assert the stable fields shared by successful/error API responses."""

    assert set(body) == {"success", "requestId", "timestamp", "data", "error"}
    assert isinstance(body["success"], bool)
    if success is not None:
        assert body["success"] is success

    assert isinstance(body["requestId"], str) and body["requestId"]
    # The middleware normally generates UUID request IDs.  This also catches
    # accidental timestamp/object values without coupling tests to formatting.
    UUID(body["requestId"])
    parsed_timestamp = datetime.fromisoformat(body["timestamp"].replace("Z", "+00:00"))
    assert parsed_timestamp.tzinfo is not None

    if body["success"]:
        assert body["error"] is None
        assert body["data"] is not None
    else:
        assert body["error"] is not None
        assert set(body["error"]) == {"code", "message"}
        assert isinstance(body["error"]["code"], str)
        assert isinstance(body["error"]["message"], str)


@pytest.mark.asyncio
async def test_health_is_public_and_reports_connected_bridge(
    client: AsyncClient,
    mock_manager_connected,
) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    _assert_envelope(body, success=True)
    assert body["data"]["connectionState"] == "CONNECTED"
    assert body["data"]["mt5Initialized"] is True
    assert response.headers["x-request-id"] == body["requestId"]


@pytest.mark.asyncio
async def test_health_reports_structured_not_ready_state(
    client: AsyncClient,
    mock_manager_disconnected,
) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    _assert_envelope(body, success=False)
    # Health intentionally retains diagnostic data on a not-ready response.
    assert body["data"]["connectionState"] == "FAILED"
    assert body["error"]["code"] == "CONNECTION_NOT_READY"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,content_type,marker",
    [
        ("/docs", "text/html", "swagger-ui"),
        ("/redoc", "text/html", "redoc"),
    ],
)
async def test_documentation_pages_are_public(
    client: AsyncClient,
    path: str,
    content_type: str,
    marker: str,
) -> None:
    response = await client.get(path)

    assert response.status_code == 200
    assert content_type in response.headers["content-type"]
    assert marker in response.text.lower()


@pytest.mark.asyncio
async def test_openapi_is_public_and_describes_bearer_protected_api(
    client: AsyncClient,
) -> None:
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "WealthBuilder Bridge"
    assert schema["components"]["securitySchemes"]["BearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
    }
    assert schema["paths"]["/health"]["get"].get("security") in (None, [])
    for path in (
        "/api/account",
        "/api/positions",
        "/api/symbols",
        "/api/market/{symbol}",
        "/api/history",
        "/api/trade/open",
    ):
        operations = schema["paths"][path]
        for operation in operations.values():
            if isinstance(operation, dict) and "responses" in operation:
                assert operation["security"] == [{"BearerAuth": []}]


@pytest.mark.asyncio
async def test_request_id_is_preserved_in_header_and_envelope(
    client: AsyncClient,
    mock_manager_connected,
) -> None:
    request_id = "2de7c9a9-7bb8-48d7-bf4b-9c4f3f18b3e1"
    response = await client.get(
        "/api/account",
        headers={**AUTH_HEADER, "X-Request-Id": request_id},
    )

    assert response.status_code == 200
    body = response.json()
    _assert_envelope(body, success=True)
    assert body["requestId"] == request_id
    assert response.headers["x-request-id"] == request_id


_PROTECTED_REQUESTS = [
    ("GET", "/api/account", None),
    ("GET", "/api/positions", None),
    ("GET", "/api/symbols", None),
    ("GET", "/api/market/EURUSD", None),
    (
        "GET",
        "/api/history?start=2026-08-27T00:00:00%2B00:00&end=2026-08-28T00:00:00%2B00:00",
        None,
    ),
    (
        "POST",
        "/api/trade/open",
        {"symbol": "EURUSD", "type": "BUY", "volume": 0.1},
    ),
    ("PUT", "/api/trade/1/modify", {"stopLoss": 1.09}),
    ("DELETE", "/api/trade/1/close", None),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,payload", _PROTECTED_REQUESTS)
async def test_protected_routes_reject_missing_authentication(
    client: AsyncClient,
    method: str,
    path: str,
    payload: dict | None,
) -> None:
    request_kwargs = {"headers": {}}
    if payload is not None:
        request_kwargs["json"] = payload
    response = await client.request(method, path, **request_kwargs)

    assert response.status_code == 401
    body = response.json()
    _assert_envelope(body, success=False)
    assert body["error"]["code"] == "AUTHENTICATION_FAILED"


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,payload", _PROTECTED_REQUESTS)
async def test_protected_routes_reject_invalid_authentication(
    client: AsyncClient,
    method: str,
    path: str,
    payload: dict | None,
) -> None:
    request_kwargs = {"headers": WRONG_AUTH_HEADER}
    if payload is not None:
        request_kwargs["json"] = payload
    response = await client.request(method, path, **request_kwargs)

    assert response.status_code == 401
    body = response.json()
    _assert_envelope(body, success=False)
    assert body["error"]["code"] == "AUTHENTICATION_FAILED"


@pytest.mark.asyncio
async def test_account_read_returns_fixture_data_in_canonical_envelope(
    client: AsyncClient,
    mock_manager_connected,
    sample_account,
) -> None:
    response = await client.get("/api/account", headers=AUTH_HEADER)

    assert response.status_code == 200
    body = response.json()
    _assert_envelope(body, success=True)
    assert body["data"]["account"] == sample_account["login"]
    assert body["data"]["balance"] == sample_account["balance"]
    assert body["data"]["equity"] == sample_account["equity"]
    assert body["data"]["free_margin"] == sample_account["margin_free"]


@pytest.mark.asyncio
async def test_positions_read_returns_fixture_data_in_canonical_envelope(
    client: AsyncClient,
    mock_manager_connected,
    sample_positions,
) -> None:
    response = await client.get("/api/positions", headers=AUTH_HEADER)

    assert response.status_code == 200
    body = response.json()
    _assert_envelope(body, success=True)
    assert len(body["data"]) == len(sample_positions)
    assert body["data"][0]["ticket"] == sample_positions[0]["ticket"]
    assert body["data"][0]["symbol"] == sample_positions[0]["symbol"]
    assert body["data"][0]["profit"] == sample_positions[0]["profit"]


@pytest.mark.asyncio
async def test_symbols_read_returns_fixture_data_in_canonical_envelope(
    client: AsyncClient,
    mock_manager_connected,
    sample_symbols,
) -> None:
    response = await client.get("/api/symbols", headers=AUTH_HEADER)

    assert response.status_code == 200
    body = response.json()
    _assert_envelope(body, success=True)
    assert len(body["data"]) == len(sample_symbols)
    assert body["data"][0]["name"] == sample_symbols[0]["name"]
    assert body["data"][0]["digits"] == sample_symbols[0]["digits"]


@pytest.mark.asyncio
async def test_market_read_returns_fixture_data_in_canonical_envelope(
    client: AsyncClient,
    mock_manager_connected,
    sample_tick,
    sample_symbol_info,
) -> None:
    response = await client.get("/api/market/EURUSD", headers=AUTH_HEADER)

    assert response.status_code == 200
    body = response.json()
    _assert_envelope(body, success=True)
    assert body["data"]["bid"] == sample_tick["bid"]
    assert body["data"]["ask"] == sample_tick["ask"]
    assert body["data"]["digits"] == sample_symbol_info["digits"]
    assert body["data"]["spread"] == pytest.approx(
        sample_tick["ask"] - sample_tick["bid"]
    )


@pytest.mark.asyncio
async def test_history_read_returns_fixture_data_in_canonical_envelope(
    client: AsyncClient,
    mock_manager_connected,
    sample_deals_and_orders,
) -> None:
    start = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    end = datetime.now(timezone.utc).isoformat()
    response = await client.get(
        "/api/history",
        params={"start": start, "end": end},
        headers=AUTH_HEADER,
    )

    assert response.status_code == 200
    body = response.json()
    _assert_envelope(body, success=True)
    assert set(body["data"]) == {"deals", "orders"}
    assert body["data"]["deals"][0]["ticket"] == sample_deals_and_orders["deals"][0]["ticket"]
    assert body["data"]["orders"][0]["ticket"] == sample_deals_and_orders["orders"][0]["ticket"]


@pytest.mark.asyncio
async def test_read_endpoint_reports_structured_error_when_bridge_is_unavailable(
    client: AsyncClient,
    mock_manager_disconnected,
) -> None:
    response = await client.get("/api/account", headers=AUTH_HEADER)

    assert response.status_code == 200
    body = response.json()
    _assert_envelope(body, success=False)
    assert body["error"]["code"] == "BRIDGE_NOT_CONNECTED"


_TRADE_MUTATIONS = [
    (
        "POST",
        "/api/trade/open",
        {"symbol": "EURUSD", "type": "BUY", "volume": 0.1},
    ),
    ("PUT", "/api/trade/1/modify", {"stopLoss": 1.09}),
    ("DELETE", "/api/trade/1/close", None),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,payload", _TRADE_MUTATIONS)
async def test_trade_mutations_are_locked_without_invoking_service(
    client: AsyncClient,
    mock_manager_connected,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    payload: dict | None,
) -> None:
    """The default lock rejects mutation requests before execution code runs."""

    from services import trade_service

    monkeypatch.setattr(settings, "BROKER_TRADING_ENABLED", False, raising=False)

    def _must_not_execute(*args, **kwargs):
        raise AssertionError("trade execution was reached while trading was locked")

    method_name = {
        "POST": "open_trade",
        "PUT": "modify_trade",
        "DELETE": "close_trade",
    }[method]
    monkeypatch.setattr(trade_service.TradeService, method_name, _must_not_execute)

    request_kwargs = {"headers": AUTH_HEADER}
    if payload is not None:
        request_kwargs["json"] = payload
    response = await client.request(method, path, **request_kwargs)

    assert response.status_code == 403
    body = response.json()
    _assert_envelope(body, success=False)
    assert body["error"]["code"] == "TRADING_DISABLED"


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,payload", _TRADE_MUTATIONS)
async def test_trade_mutations_map_read_only_service_to_501(
    client: AsyncClient,
    mock_manager_connected,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    payload: dict | None,
) -> None:
    """Even when the gate is opened in a test, no trade execution exists."""

    monkeypatch.setattr(settings, "BROKER_TRADING_ENABLED", True, raising=False)

    request_kwargs = {"headers": AUTH_HEADER}
    if payload is not None:
        request_kwargs["json"] = payload
    response = await client.request(method, path, **request_kwargs)

    assert response.status_code == 501
    body = response.json()
    _assert_envelope(body, success=False)
    assert body["error"]["code"] == "NOT_IMPLEMENTED"
