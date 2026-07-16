"""
WealthBuilder Bridge — Phase 2.1 test suite.

Validates the following criteria:

  - Application starts and shuts down cleanly.
  - Swagger UI (GET /docs) loads.
  - ReDoc UI (GET /redoc) loads.
  - Health endpoint returns HTTP 200 with the expected payload shape.
  - Every protected endpoint returns HTTP 401 when no token is provided.
  - No endpoint returns HTTP 500.
  - Repository imports without error.

Run with::

    pytest bridge/tests/ -v
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Environment bootstrap — must happen before bridge.config is imported.
# ---------------------------------------------------------------------------

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("API_VERSION", "v1")
os.environ.setdefault("AUTH_TOKEN", "test-secret-token-for-pytest")
os.environ.setdefault("LOG_LEVEL", "WARNING")

from bridge.app import app  # noqa: E402  (env vars must be set first)

_AUTH_HEADER = {"Authorization": f"Bearer {os.environ['AUTH_TOKEN']}"}
_BAD_HEADER: dict[str, str] = {}  # no auth header


@pytest_asyncio.fixture()
async def client() -> AsyncClient:
    """Provide an async test client with a running lifespan."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_application_starts_and_is_ready(client: AsyncClient) -> None:
    """The application lifespan completes without error and the bridge is READY."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["bridgeStatus"] == "READY"


# ---------------------------------------------------------------------------
# OpenAPI / documentation endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_swagger_ui_loads(client: AsyncClient) -> None:
    """GET /docs returns 200 and HTML content."""
    response = await client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_redoc_loads(client: AsyncClient) -> None:
    """GET /redoc returns 200 and HTML content."""
    response = await client.get("/redoc")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient) -> None:
    """GET /health returns HTTP 200 without requiring authentication."""
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_response_shape(client: AsyncClient) -> None:
    """Health response contains all required envelope and payload fields."""
    response = await client.get("/health")
    body = response.json()

    assert body["success"] is True
    assert "requestId" in body
    assert "timestamp" in body

    data = body["data"]
    assert "applicationName" in data
    assert "applicationVersion" in data
    assert "apiVersion" in data
    assert "environment" in data
    assert "startupTime" in data
    assert "uptimeSeconds" in data
    assert "bridgeStatus" in data


@pytest.mark.asyncio
async def test_health_includes_request_id_header(client: AsyncClient) -> None:
    """GET /health response includes X-Request-ID header."""
    response = await client.get("/health")
    assert "x-request-id" in response.headers


@pytest.mark.asyncio
async def test_health_returns_ready_status(client: AsyncClient) -> None:
    """Bridge status in health payload is READY after startup."""
    response = await client.get("/health")
    assert response.json()["data"]["bridgeStatus"] == "READY"


# ---------------------------------------------------------------------------
# Authentication — protected endpoints must reject unauthenticated requests
# ---------------------------------------------------------------------------


_PROTECTED_ROUTES = [
    ("GET", "/api/account"),
    ("GET", "/api/account/balance"),
    ("GET", "/api/account/margin"),
    ("GET", "/api/positions"),
    ("GET", "/api/positions/1"),
    ("GET", "/api/symbols"),
    ("GET", "/api/symbols/EURUSD"),
    ("GET", "/api/market/EURUSD/tick"),
    ("GET", "/api/market/EURUSD/rates"),
    ("POST", "/api/trade/open"),
    ("PUT", "/api/trade/1/modify"),
    ("DELETE", "/api/trade/1/close"),
    ("GET", "/api/history/deals"),
    ("GET", "/api/history/orders"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", _PROTECTED_ROUTES)
async def test_protected_endpoint_returns_401_without_token(
    client: AsyncClient,
    method: str,
    path: str,
) -> None:
    """Every protected endpoint returns HTTP 401 when no Authorization header is sent."""
    response = await client.request(method, path, headers=_BAD_HEADER)
    assert response.status_code == 401, (
        f"{method} {path} expected 401, got {response.status_code}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", _PROTECTED_ROUTES)
async def test_protected_endpoint_returns_401_with_wrong_token(
    client: AsyncClient,
    method: str,
    path: str,
) -> None:
    """Every protected endpoint returns HTTP 401 when an invalid token is used."""
    response = await client.request(
        method, path, headers={"Authorization": "Bearer wrong-token"}
    )
    assert response.status_code == 401, (
        f"{method} {path} expected 401, got {response.status_code}"
    )


# ---------------------------------------------------------------------------
# Stub endpoints — authenticated requests must return 501 (not 500)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", _PROTECTED_ROUTES)
async def test_authenticated_stub_returns_501_not_500(
    client: AsyncClient,
    method: str,
    path: str,
) -> None:
    """Authenticated requests to stub endpoints return 501 — never 500."""
    response = await client.request(method, path, headers=_AUTH_HEADER)
    assert response.status_code == 501, (
        f"{method} {path} expected 501, got {response.status_code}: {response.text}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", _PROTECTED_ROUTES)
async def test_stub_response_shape(
    client: AsyncClient,
    method: str,
    path: str,
) -> None:
    """Stub responses use the standard BridgeResponse envelope."""
    response = await client.request(method, path, headers=_AUTH_HEADER)
    body = response.json()

    assert body["success"] is False
    assert "requestId" in body
    assert "timestamp" in body
    assert body["error"]["code"] == "NOT_IMPLEMENTED"


# ---------------------------------------------------------------------------
# Repository compile check
# ---------------------------------------------------------------------------


def test_core_modules_import_cleanly() -> None:
    """All core modules import without raising an exception."""
    import bridge.core.auth  # noqa: F401
    import bridge.core.connection_manager  # noqa: F401
    import bridge.core.exceptions  # noqa: F401
    import bridge.core.logging  # noqa: F401
    import bridge.core.models  # noqa: F401
    import bridge.core.request_context  # noqa: F401
    import bridge.core.responses  # noqa: F401


def test_service_modules_import_cleanly() -> None:
    """All service modules import without raising an exception."""
    import bridge.services.account_service  # noqa: F401
    import bridge.services.history_service  # noqa: F401
    import bridge.services.market_service  # noqa: F401
    import bridge.services.position_service  # noqa: F401
    import bridge.services.symbol_service  # noqa: F401
    import bridge.services.trade_service  # noqa: F401


def test_middleware_modules_import_cleanly() -> None:
    """All middleware modules import without raising an exception."""
    import bridge.middleware.auth  # noqa: F401
    import bridge.middleware.logging  # noqa: F401
    import bridge.middleware.request_id  # noqa: F401
    import bridge.middleware.timing  # noqa: F401
