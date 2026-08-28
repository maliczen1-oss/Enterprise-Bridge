# tests/test_services.py
from __future__ import annotations

import pytest

from services import position_service, market_service, symbol_service, history_service


@pytest.mark.asyncio
async def test_position_service_handles_empty(monkeypatch):
    class FakeManager:
        def fetch_positions(self):
            return None

    monkeypatch.setattr("core.connection_manager.manager", FakeManager())
    out = position_service.get_positions()
    assert isinstance(out, list)
    assert out == []


@pytest.mark.asyncio
async def test_market_service_handles_missing(monkeypatch):
    class FakeManager:
        def fetch_symbol_tick(self, symbol):
            return None

        def fetch_symbol_info(self, symbol):
            return None

    monkeypatch.setattr("core.connection_manager.manager", FakeManager())
    out = market_service.get_market("EURUSD")
    assert out is None


@pytest.mark.asyncio
async def test_symbol_service_handles_missing(monkeypatch):
    class FakeManager:
        def fetch_symbols(self):
            return None

    monkeypatch.setattr("core.connection_manager.manager", FakeManager())
    out = symbol_service.get_symbols()
    assert isinstance(out, list)
    assert out == []


@pytest.mark.asyncio
async def test_history_service_handles_missing(monkeypatch):
    class FakeManager:
        def get_state(self):
            return "CONNECTED"

        def get_last_error(self):
            return None

        def fetch_history_deals(self, from_dt, to_dt, **k):
            return None

        def fetch_history_orders(self, from_dt, to_dt, **k):
            return None

    monkeypatch.setattr("core.connection_manager.manager", FakeManager())
    import datetime

    out = history_service.get_history(datetime.datetime.utcnow(), datetime.datetime.utcnow())
    assert "deals" in out and "orders" in out
    assert out["deals"] == [] and out["orders"] == []
