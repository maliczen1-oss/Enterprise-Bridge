# tests/test_services.py
import datetime
from typing import Any, Dict, List

import pytest

from services import account_service, position_service, symbol_service, market_service, history_service


def test_account_service_connected(mock_manager_connected):
    data = account_service.get_account()
    assert data is not None
    assert data["account"] == 123456
    assert data["balance"] == 10000.0
    assert data["currency"] == "USD"


def test_account_service_disconnected(mock_manager_disconnected):
    data = account_service.get_account()
    assert data is None


def test_positions_service_connected(mock_manager_connected):
    positions = position_service.get_positions()
    assert isinstance(positions, list)
    assert len(positions) == 1
    p = positions[0]
    assert p["symbol"] == "EURUSD"
    assert p["profit"] == 10.0


def test_positions_service_disconnected(mock_manager_disconnected):
    positions = position_service.get_positions()
    assert isinstance(positions, list)
    assert len(positions) == 0


def test_symbols_service_connected(mock_manager_connected):
    syms = symbol_service.get_symbols()
    assert isinstance(syms, list)
    assert syms[0]["name"] == "EURUSD"
    assert syms[0]["currency"] == "USD"


def test_symbols_service_disconnected(mock_manager_disconnected):
    syms = symbol_service.get_symbols()
    assert isinstance(syms, list)
    assert len(syms) == 0


def test_market_service_connected(mock_manager_connected):
    res = market_service.get_market("EURUSD")
    assert res is not None
    assert res["bid"] == 1.1010
    assert res["ask"] == 1.1012
    assert res["digits"] == 5


def test_market_service_unknown_symbol(mock_manager_connected):
    res = market_service.get_market("UNKNOWN")
    assert res is None


def test_market_service_disconnected(mock_manager_disconnected):
    res = market_service.get_market("EURUSD")
    assert res is None


def test_history_service_connected(mock_manager_connected):
    now = datetime.datetime.utcnow()
    earlier = now - datetime.timedelta(days=1)
    res = history_service.get_history(earlier, now, ticket=None, symbol=None, limit=None)
    assert isinstance(res, dict)
    assert "deals" in res and "orders" in res
    assert len(res["deals"]) == 1
    assert len(res["orders"]) == 1


def test_history_service_disconnected(mock_manager_disconnected):
    now = datetime.datetime.utcnow()
    earlier = now - datetime.timedelta(days=1)
    res = history_service.get_history(earlier, now, ticket=None, symbol=None, limit=None)
    assert isinstance(res, dict)
    assert res["deals"] == []
    assert res["orders"] == []
