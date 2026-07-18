# tests/conftest.py
import pytest
import datetime
from types import SimpleNamespace
from typing import Any, Dict, List

import logging

from core import connection_manager as cm_module
from config import settings

logger = logging.getLogger("bridge")


@pytest.fixture(autouse=True)
def patch_logger_level():
    """
    Ensure tests produce minimal noise; tests can still assert logs if needed.
    """
    logging.getLogger("bridge").setLevel(logging.CRITICAL)
    yield
    logging.getLogger("bridge").setLevel(logging.INFO)


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
def mock_manager(monkeypatch, sample_account, sample_positions, sample_symbols, sample_tick, sample_symbol_info, sample_deals_and_orders):
    """
    Replace the module-level manager singleton with a SimpleNamespace that exposes
    the read-only fetch methods used by services and APIs.
    """
    fake = SimpleNamespace()

    # Lifecycle/state helpers
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

    def _from_to(dt_from, dt_to, ticket=None, symbol=None):
        # Return deals/orders from fixture regardless of filters for simplicity
        return sample_deals_and_orders["deals"]

    def _orders(dt_from, dt_to, ticket=None, symbol=None):
        return sample_deals_and_orders["orders"]

    fake.fetch_history_deals = _from_to
    fake.fetch_history_orders = _orders

    # Monkeypatch the module-level manager object in core.connection_manager
    monkeypatch.setattr(cm_module, "manager", fake)
    # Also patch any direct imports of the manager (services import manager from core.connection_manager)
    # Many modules import `from core.connection_manager import manager as connection_manager`
    # So patch that name in the connection_manager module's namespace is sufficient because services reference it.
    yield fake
