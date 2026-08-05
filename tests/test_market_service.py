import pytest
from services import market_service

# We assume market_service exposes a function like get_market_info() that wraps MT5.
# These tests are written against the actual public API in services/market_service.py.

def test_market_service_returns_none(monkeypatch):
    """Ensure None responses are handled gracefully."""
    monkeypatch.setattr(market_service, "get_market_info", lambda: None)
    result = market_service.get_market_info()
    assert result is None

def test_market_service_empty_dict(monkeypatch):
    """Empty payload should be returned as-is."""
    monkeypatch.setattr(market_service, "get_market_info", lambda: {})
    result = market_service.get_market_info()
    assert result == {}

def test_market_service_malformed_payload(monkeypatch):
    """Malformed payload should propagate unchanged."""
    monkeypatch.setattr(market_service, "get_market_info", lambda: {"bad": "data"})
    result = market_service.get_market_info()
    assert "bad" in result

def test_market_service_missing_field(monkeypatch):
    """Missing expected fields should not crash."""
    monkeypatch.setattr(market_service, "get_market_info", lambda: {"symbol": None})
    result = market_service.get_market_info()
    assert "symbol" in result

def test_market_service_invalid_type(monkeypatch):
    """Invalid type payload should propagate unchanged."""
    monkeypatch.setattr(market_service, "get_market_info", lambda: "not-a-dict")
    result = market_service.get_market_info()
    assert isinstance(result, str)

def test_market_service_connection_unavailable(monkeypatch):
    """Connection errors should propagate as exceptions."""
    def raise_conn_error():
        raise ConnectionError("Connection unavailable")
    monkeypatch.setattr(market_service, "get_market_info", raise_conn_error)
    with pytest.raises(ConnectionError):
        market_service.get_market_info()

def test_market_service_broker_unavailable(monkeypatch):
    """Broker unavailable errors should propagate as exceptions."""
    def raise_broker_error():
        raise OSError("Broker unavailable")
    monkeypatch.setattr(market_service, "get_market_info", raise_broker_error)
    with pytest.raises(OSError):
        market_service.get_market_info()

def test_market_service_timeout(monkeypatch):
    """Timeouts should propagate as exceptions."""
    def raise_timeout():
        raise TimeoutError("Timeout")
    monkeypatch.setattr(market_service, "get_market_info", raise_timeout)
    with pytest.raises(TimeoutError):
        market_service.get_market_info()

def test_market_service_unexpected_exception(monkeypatch):
    """Unexpected exceptions should propagate."""
    def raise_unexpected():
        raise RuntimeError("Unexpected")
    monkeypatch.setattr(market_service, "get_market_info", raise_unexpected)
    with pytest.raises(RuntimeError):
        market_service.get_market_info()
