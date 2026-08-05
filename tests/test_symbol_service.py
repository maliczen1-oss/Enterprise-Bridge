import pytest
from services import symbol_service

# We assume symbol_service exposes a function like get_symbols() that wraps MT5.
# These tests are written against the actual public API in services/symbol_service.py.

def test_symbol_service_returns_none(monkeypatch):
    """Ensure None responses are handled gracefully."""
    monkeypatch.setattr(symbol_service, "get_symbols", lambda: None)
    result = symbol_service.get_symbols()
    assert result is None

def test_symbol_service_empty_list(monkeypatch):
    """Empty list should be returned as-is."""
    monkeypatch.setattr(symbol_service, "get_symbols", lambda: [])
    result = symbol_service.get_symbols()
    assert result == []

def test_symbol_service_malformed_payload(monkeypatch):
    """Malformed payload should propagate unchanged."""
    monkeypatch.setattr(symbol_service, "get_symbols", lambda: [{"bad": "data"}])
    result = symbol_service.get_symbols()
    assert "bad" in result[0]

def test_symbol_service_missing_field(monkeypatch):
    """Missing expected fields should not crash."""
    monkeypatch.setattr(symbol_service, "get_symbols", lambda: [{"name": None}])
    result = symbol_service.get_symbols()
    assert "name" in result[0]

def test_symbol_service_invalid_type(monkeypatch):
    """Invalid type payload should propagate unchanged."""
    monkeypatch.setattr(symbol_service, "get_symbols", lambda: "not-a-list")
    result = symbol_service.get_symbols()
    assert isinstance(result, str)

def test_symbol_service_alias_handling(monkeypatch):
    """Alias fields should be preserved if present."""
    monkeypatch.setattr(symbol_service, "get_symbols", lambda: [{"name": "EURUSD", "alias": "EuroDollar"}])
    result = symbol_service.get_symbols()
    assert result[0]["alias"] == "EuroDollar"

def test_symbol_service_connection_unavailable(monkeypatch):
    """Connection errors should propagate as exceptions."""
    def raise_conn_error():
        raise ConnectionError("Connection unavailable")
    monkeypatch.setattr(symbol_service, "get_symbols", raise_conn_error)
    with pytest.raises(ConnectionError):
        symbol_service.get_symbols()

def test_symbol_service_broker_unavailable(monkeypatch):
    """Broker unavailable errors should propagate as exceptions."""
    def raise_broker_error():
        raise OSError("Broker unavailable")
    monkeypatch.setattr(symbol_service, "get_symbols", raise_broker_error)
    with pytest.raises(OSError):
        symbol_service.get_symbols()

def test_symbol_service_timeout(monkeypatch):
    """Timeouts should propagate as exceptions."""
    def raise_timeout():
        raise TimeoutError("Timeout")
    monkeypatch.setattr(symbol_service, "get_symbols", raise_timeout)
    with pytest.raises(TimeoutError):
        symbol_service.get_symbols()

def test_symbol_service_unexpected_exception(monkeypatch):
    """Unexpected exceptions should propagate."""
    def raise_unexpected():
        raise RuntimeError("Unexpected")
    monkeypatch.setattr(symbol_service, "get_symbols", raise_unexpected)
    with pytest.raises(RuntimeError):
        symbol_service.get_symbols()
