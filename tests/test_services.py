# tests/test_services.py
import datetime
from typing import Any, Dict, List

import pytest

from services import account_service, position_service, symbol_service, market_service, history_service


def test_get_account_returns_expected_fields(mock_manager):
    data = account_service.get_account()
    assert data is not None
    # Basic presence checks
    assert "account" in data
    assert "balance" in data
    assert "equity" in data
    assert data["currency"] == "USD"


def test_get_positions_returns_list_and_fields(mock_manager):
    positions = position_service.get_positions()
    assert isinstance(positions, list)
    assert len(positions) == 1
    p = positions[0]
    assert "ticket" in p
    assert p["symbol"] == "EURUSD"
    assert p["profit"] == 10.0


def test_get_symbols_returns_list(mock_manager):
    syms = symbol_service.get_symbols()
    assert isinstance(syms, list)
    assert len(syms) == 1
    s = syms[0]
    assert s["name"] == "EURUSD"
    assert s["currency"] == "USD"


def test_get_market_returns_combined_tick_and_info(mock_manager):
    result = market_service.get_market("EURUSD")
    assert result is not None
    assert result["bid"] == 1.1010
    assert result["ask"] == 1.1012
    assert result["digits"] == 5
    assert result["point"] == 0.00001


def test_get_history_returns_deals_and_orders(mock_manager):
    now = datetime.datetime.utcnow()
    earlier = now - datetime.timedelta(days=1)
    res = history_service.get_history(earlier, now, ticket=None, symbol=None, limit=None)
    assert isinstance(res, dict)
    assert "deals" in res and "orders" in res
    assert len(res["deals"]) == 1
    assert len(res["orders"]) == 1
