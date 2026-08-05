import pytest
from services import position_service

def test_position_service_returns_none(monkeypatch):
    monkeypatch.setattr(position_service, "get_positions", lambda: None)
    result = position_service.get_positions()
    assert result is None

def test_position_service_empty_list(monkeypatch):
    monkeypatch.setattr(position_service, "get_positions", lambda: [])
    result = position_service.get_positions()
    assert result == []

def test_position_service_malformed_payload(monkeypatch):
    monkeypatch.setattr(position_service, "get_positions", lambda: [{"bad": "data"}])
    result = position_service.get_positions()
    assert "bad" in result[0]

def test_position_service_missing_field(monkeypatch):
    monkeypatch.setattr(position_service, "get_positions", lambda: [{"ticket": None}])
    result = position_service.get_positions()
    assert "ticket" in result[0]

def test_position_service_invalid_type(monkeypatch):
    monkeypatch.setattr(position_service, "get_positions", lambda: "not-a-list")
    result = position_service.get_positions()
    assert isinstance(result, str)

def test_position_service_connection_unavailable(monkeypatch):
    def raise_conn_error():
        raise ConnectionError("Connection unavailable")
    monkeypatch.setattr(position_service, "get_positions", raise_conn_error)
    with pytest.raises(ConnectionError):
        position_service.get_positions()

def test_position_service_broker_unavailable(monkeypatch):
    def raise_broker_error():
        raise OSError("Broker unavailable")
    monkeypatch.setattr(position_service, "get_positions", raise_broker_error)
    with pytest.raises(OSError):
        position_service.get_positions()

def test_position_service_timeout(monkeypatch):
    def raise_timeout():
        raise TimeoutError("Timeout")
    monkeypatch.setattr(position_service, "get_positions", raise_timeout)
    with pytest.raises(TimeoutError):
        position_service.get_positions()

def test_position_service_unexpected_exception(monkeypatch):
    def raise_unexpected():
        raise RuntimeError("Unexpected")
    monkeypatch.setattr(position_service, "get_positions", raise_unexpected)
    with pytest.raises(RuntimeError):
        position_service.get_positions()
