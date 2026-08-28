# tests/conftest.py
import pytest
import pytest_asyncio
import datetime
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
import logging
import platform
from httpx import ASGITransport, AsyncClient

import core.connection_manager as cm_module
from config import settings


class _ManagerProxy:
    """Keep imported manager aliases pointed at the test-selected manager.

    Runtime modules import ``manager`` by value.  Tests replace
    ``core.connection_manager.manager`` with a fake, so a small delegating
    proxy keeps the API and service aliases synchronized without changing
    production code.
    """

    def __getattr__(self, name):
        return getattr(cm_module.manager, name)


@pytest.fixture(autouse=True)
def patch_imported_manager_aliases(monkeypatch):
    proxy = _ManagerProxy()
    modules = [
        "app",
        "api.health",
        "api.account",
        "api.positions",
        "api.symbols",
        "api.market",
        "api.trade",
        "services.account_service",
        "services.position_service",
        "services.symbol_service",
        "services.market_service",
        "services.history_service",
    ]
    import importlib
    for module_name in modules:
        module = importlib.import_module(module_name)
        if hasattr(module, "connection_manager"):
            monkeypatch.setattr(module, "connection_manager", proxy)
    yield


@pytest_asyncio.fixture
async def client():
    """Modern async ASGI client shared by endpoint tests."""
    from bridge.app import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac

# Let caplog select the level per test; globally forcing CRITICAL hides the
# INFO/DEBUG behavior that the service tests intentionally verify.
logging.getLogger("bridge").setLevel(logging.NOTSET)


@pytest.fixture(autouse=True)
def ensure_test_auth_token(monkeypatch):
    """
    Ensure a stable AUTH_TOKEN for tests so they don't depend on environment.
    """
    monkeypatch.setattr(settings, "AUTH_TOKEN", "test-token", raising=False)
    yield


@pytest.fixture
def sample_account() -> Dict[str, Any]:
    return {
        "login": 123456,
        "server": "DemoServer",
        "company": "DemoBroker",
        "balance": 10000.0,
        "equity": 10050.0,
        "margin": 100.0,
        "margin_free": 9950.0,
        "margin_level": 10050.0,
        "currency": "USD",
        "leverage": 100,
        "name": "Demo Account",
    }


@pytest.fixture
def sample_positions() -> List[Dict[str, Any]]:
    return [
        {
            "ticket": 1,
            "symbol": "EURUSD",
            "type": 0,
            "volume": 0.1,
            "price_open": 1.1000,
            "price_current": 1.1010,
            "profit": 10.0,
            "swap": 0.0,
            "commission": 0.0,
            "sl": 1.0900,
            "tp": 1.1200,
            "time": 1620000000,
            "magic": 42,
            "comment": "test",
        }
    ]


@pytest.fixture
def sample_symbols() -> List[Dict[str, Any]]:
    return [
        {
            "name": "EURUSD",
            "visible": True,
            "trade_mode": "FOREX",
            "digits": 5,
            "point": 0.00001,
            "spread": 1.2,
            "contract_size": 100000,
            "currency": "USD",
        }
    ]


@pytest.fixture
def sample_tick() -> Dict[str, Any]:
    return {
        "bid": 1.1010,
        "ask": 1.1012,
        "time": 1620000000,
        "volume": 1000,
    }


@pytest.fixture
def sample_symbol_info() -> Dict[str, Any]:
    return {
        "digits": 5,
        "point": 0.00001,
        "high": 1.1050,
        "low": 1.0950,
    }


@pytest.fixture
def sample_deals_and_orders() -> Dict[str, Any]:
    deals = [
        {
            "ticket": 1001,
            "symbol": "EURUSD",
            "profit": 5.0,
            "commission": 0.0,
            "swap": 0.0,
            "comment": "deal1",
            "time": 1620001000,
        }
    ]
    orders = [
        {
            "ticket": 2001,
            "symbol": "EURUSD",
            "profit": 0.0,
            "commission": 0.0,
            "swap": 0.0,
            "comment": "order1",
            "time": 1620002000,
        }
    ]
    return {"deals": deals, "orders": orders}


@pytest.fixture
def mock_manager_connected(
    monkeypatch,
    sample_account,
    sample_positions,
    sample_symbols,
    sample_tick,
    sample_symbol_info,
    sample_deals_and_orders,
):
    """
    Provide a fake manager in CONNECTED state. Services and APIs should use this.
    """
    fake = SimpleNamespace()

    # Health and state
    fake.get_health = lambda: {
        "connectionState": "CONNECTED",
        "mt5Initialized": True,
        "terminalVersion": "5.0.37",
        "lastError": None,
        "startupTime": 0.0,
    }
    fake.get_state = lambda: "CONNECTED"
    fake.is_connected = lambda: True

    # Read-only proxies
    fake.fetch_account = lambda: sample_account
    fake.fetch_positions = lambda: sample_positions
    fake.fetch_symbols = lambda: sample_symbols
    fake.fetch_symbol_info = lambda symbol: sample_symbol_info if symbol == "EURUSD" else None
    fake.fetch_symbol_tick = lambda symbol: sample_tick if symbol == "EURUSD" else None

    def _deals(from_dt, to_dt, ticket=None, symbol=None):
        return sample_deals_and_orders["deals"]

    def _orders(from_dt, to_dt, ticket=None, symbol=None):
        return sample_deals_and_orders["orders"]

    fake.fetch_history_deals = _deals
    fake.fetch_history_orders = _orders

    # Capabilities: pretend platform supports and MT5 available
    fake.get_capabilities = lambda: {
        "platform": "windows",
        "mt5Supported": True,
        "mt5Available": True,
        "backend": "enabled",
        "state": "CONNECTED",
        "mt5Initialized": True,
        "terminalVersion": "5.0.37",
        "lastError": None,
    }

    monkeypatch.setattr(cm_module, "manager", fake)
    yield fake


@pytest.fixture
def mock_manager_disconnected(monkeypatch):
    """
    Provide a fake manager in DISCONNECTED/FAILED state to test error paths.
    """
    fake = SimpleNamespace()
    fake.get_health = lambda: {
        "connectionState": "FAILED",
        "mt5Initialized": False,
        "terminalVersion": None,
        "lastError": {"code": "MT5_IMPORT_FAILED", "message": "MetaTrader5 not installed"},
        "startupTime": None,
    }
    fake.get_state = lambda: "FAILED"
    fake.is_connected = lambda: False

    # Read-only proxies return None / empty lists
    fake.fetch_account = lambda: None
    fake.fetch_positions = lambda: []
    fake.fetch_symbols = lambda: []
    fake.fetch_symbol_info = lambda symbol: None
    fake.fetch_symbol_tick = lambda symbol: None
    fake.fetch_history_deals = lambda *a, **k: []
    fake.fetch_history_orders = lambda *a, **k: []

    fake.get_capabilities = lambda: {
        "platform": platform.system().lower(),
        "mt5Supported": False,
        "mt5Available": False,
        "backend": "disabled",
        "state": "FAILED",
        "mt5Initialized": False,
        "terminalVersion": None,
        "lastError": {"code": "MT5_IMPORT_FAILED", "message": "MetaTrader5 not installed"},
    }

    monkeypatch.setattr(cm_module, "manager", fake)
    yield fake


@pytest.fixture
def mock_manager_unsupported(monkeypatch):
    """
    Simulate an unsupported platform (e.g., linux where MT5 is not supported).
    """
    fake = SimpleNamespace()
    fake.get_health = lambda: {
        "connectionState": "UNSUPPORTED_PLATFORM",
        "mt5Initialized": False,
        "terminalVersion": None,
        "lastError": None,
        "startupTime": None,
    }
    fake.get_state = lambda: "UNSUPPORTED_PLATFORM"
    fake.is_connected = lambda: False

    fake.fetch_account = lambda: None
    fake.fetch_positions = lambda: []
    fake.fetch_symbols = lambda: []
    fake.fetch_symbol_info = lambda symbol: None
    fake.fetch_symbol_tick = lambda symbol: None
    fake.fetch_history_deals = lambda *a, **k: []
    fake.fetch_history_orders = lambda *a, **k: []

    fake.get_capabilities = lambda: {
        "platform": "linux",
        "mt5Supported": False,
        "mt5Available": False,
        "backend": "disabled",
        "state": "UNSUPPORTED_PLATFORM",
        "mt5Initialized": False,
        "terminalVersion": None,
        "lastError": None,
    }

    monkeypatch.setattr(cm_module, "manager", fake)
    yield fake
