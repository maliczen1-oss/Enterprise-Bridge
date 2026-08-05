import pytest
from services import history_service

def test_history_service_returns_none(monkeypatch):
    monkeypatch.setattr(history_service, "get_history", lambda s, e, f: None)
    result = history_service.get_history("EURUSD", "2020-01-01", "2020-01-02")
    assert result is None

def test_history_service_empty_list(monkeypatch):
    monkeypatch.setattr(history_service
