# tests/test_service_normalization.py
import pytest

from services import account_service, position_service


def test_account_service_handles_missing_fields(monkeypatch):
    # Provide a minimal account dict missing optional fields
    minimal = {"login": 555, "balance": 123.45}

    class FakeManager:
        def fetch_account(self):
            return minimal

    monkeypatch.setattr("core.connection_manager.manager", FakeManager())

    acc = account_service.get_account()
    assert acc is not None
    assert acc.get("account") == 555
    # missing fields should be present as None or absent but not raise
    assert "currency" in acc


def test_positions_service_handles_missing_fields(monkeypatch):
    # Position missing many optional fields
    minimal_pos = [{"ticket": 9, "symbol": "EURUSD"}]

    class FakeManager:
        def fetch_positions(self):
            return minimal_pos

    monkeypatch.setattr("core.connection_manager.manager", FakeManager())

    positions = position_service.get_positions()
    assert isinstance(positions, list)
    assert positions[0]["ticket"] == 9
    assert positions[0].get("profit") is None
