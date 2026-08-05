import pytest
from services import position_service

# We assume position_service exposes a function like get_positions() that wraps MT5.
# These tests are written against the actual public API in services/position_service.py.

def test_position_service_returns_none(monkeypatch):
    """Ensure None responses are handled gracefully."""
    monkeypatch.setattr(position_service, "get_positions", lambda: None)
    result = position_service.get_positions()
    assert result is None

def test_position_service_empty_list(monkeypatch):
    """Empty list should be returned as-is."""
    monkeypatch.setattr(position_service, "get_positions", lambda: [])
    result = position_service.get_positions()
    assert result == []

def test_position_service_malformed_payload(monkeypatch):
    """Malformed payload should propagate unchanged."""
    monkeypatch.setattr(position_service, "get_positions", lambda: [{"bad": "data"}])
    result = position_service.get_positions()
    assert "bad" in result[0]

def test_position_service_missing_field(monkeypatch):
    """Missing expected fields should not crash."""
    monkeypatch.setattr(position_service, "get_positions", lambda: [{"ticket": None}])
    result = position_service.get_positions()
    assert "ticket" in result[0]

def test_position_service_invalid_type(monkeypatch):
    """Invalid type payload should propagate unchanged."""
    monkeypatch.setattr(position_service, "get_positions", lambda: "not-a-list")
    result = position_service.get_positions()
    assert isinstance(result, str)

def test_position_service_connection_unavailable(monkeypatch):
    """Connection errors should propagate as exceptions."""
    def raise_conn_error():
        raise ConnectionError("Connection unavailable")
    monkeypatch.setattr(position_service, "get_positions", raise_conn_error)
    with pytest.raises(ConnectionError):
        position_service.get_positions()

def test_position_service_broker_unavailable(monkeypatch):
    """Broker unavailable errors should propagate as exceptions."""
    def raise_broker_error():
        raise OSError("Broker unavailable")
    monkeypatch.setattr(position_service, "get_positions", raise_broker_error)
    with pytest.raises(OSError):
        position_service.get_positions()

def test_position_service_timeout(monkeypatch):
    """Timeouts should propagate as exceptions."""
    def raise_timeout():
        raise TimeoutError("Timeout")
    monkeypatch.setattr(position_service, "get_positions", raise_timeout)
    with pytest.raises(TimeoutError):
        position_service.get_positions()

def test_position_service_unexpected_exception(monkeypatch):
    """Unexpected exceptions should propagate."""
    def raise_unexpected():
        raise RuntimeError("Unexpected")
    monkeypatch.setattr(position_service, "get_positions", raise_unexpected)
    with pytest.raises(RuntimeError):
        position_service.get_positions()
