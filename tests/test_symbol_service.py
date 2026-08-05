import pytest
from services import symbol_service

def test_symbol_service_returns_none(monkeypatch):
    monkeypatch.setattr(symbol_service, "get_symbols", lambda: None)
    result = symbol_service.get_symbols()
    assert result is None

def test_symbol_service_empty_list(monkeypatch):
    monkeypatch.setattr(symbol_service, "get_symbols", lambda: [])
    result = symbol_service.get_symbols()
    assert result == []

def test_symbol_service_malformed_payload(monkeypatch):
    monkeypatch.setattr(symbol_service, "get_symbols", lambda: [{"bad": "data"}])
    result = symbol_service.get_symbols()
    assert "bad" in result[0]

def test_symbol_service_missing_field(monkeypatch):
    monkeypatch.setattr(symbol_service, "get_symbols", lambda: [{"name": None}])
    result = symbol_service.get_symbols()
    assert "name" in result[0]

def test_symbol_service_invalid_type(monkeypatch):
    monkeypatch.setattr(symbol_service, "get_symbols", lambda: "not-a-list")
    result = symbol_service.get_symbols()
    assert isinstance(result, str)

def test_symbol_service_alias_handling(monkeypatch):
    monkeypatch.setattr(symbol_service, "get_symbols", lambda: [{"name": "EURUSD", "alias": "EuroDollar"}])
    result = symbol_service.get_symbols()
    assert result[0]["alias"] == "EuroDollar"

def test_symbol_service_connection_unavailable(monkeypatch):
    def raise_conn_error():
        raise ConnectionError("Connection unavailable")
    monkeypatch.setattr(symbol_service, "get_symbols", raise_conn_error)
    with pytest.raises(ConnectionError):
        symbol_service.get_symbols()

def test_symbol_service_broker_unavailable(monkeypatch):
    def raise_broker_error():
        raise OSError("Broker unavailable")
    monkeypatch.setattr(symbol_service, "get_symbols", raise_broker_error)
    with pytest.raises(OSError):
        symbol_service.get_symbols()

def test_symbol_service_timeout(monkeypatch):
    def raise_timeout():
        raise TimeoutError("Timeout")
    monkeypatch.setattr(symbol_service, "get_symbols", raise_timeout)
    with pytest.raises(TimeoutError):
        symbol_service.get_symbols()

def test_symbol_service_unexpected_exception(monkeypatch):
    def raise_unexpected():
        raise RuntimeError("Unexpected")
    monkeypatch.setattr(symbol_service, "get_symbols", raise_unexpected)
    with pytest.raises(RuntimeError):
        symbol_service.get_symbols()
