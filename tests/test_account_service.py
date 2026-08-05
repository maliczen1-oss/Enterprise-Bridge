import pytest
from services import account_service

def test_account_service_returns_none(monkeypatch):
    monkeypatch.setattr(account_service, "get_account", lambda: None)
    result = account_service.get_account()
    assert result is None

def test_account_service_empty_dict(monkeypatch):
    monkeypatch.setattr(account_service, "get_account", lambda: {})
    result = account_service.get_account()
    assert result == {}

def test_account_service_malformed_payload(monkeypatch):
    monkeypatch.setattr(account_service, "get_account", lambda: {"bad": "data"})
    result = account_service.get_account()
    assert "bad" in result

def test_account_service_missing_field(monkeypatch):
    monkeypatch.setattr(account_service, "get_account", lambda: {"balance": None})
    result = account_service.get_account()
    assert "balance" in result

def test_account_service_invalid_type(monkeypatch):
    monkeypatch.setattr(account_service, "get_account", lambda: "not-a-dict")
    result = account_service.get_account()
    assert isinstance(result, str)

def test_account_service_connection_unavailable(monkeypatch):
    def raise_conn_error():
        raise ConnectionError("Connection unavailable")
    monkeypatch.setattr(account_service, "get_account", raise_conn_error)
    with pytest.raises(ConnectionError):
        account_service.get_account()

def test_account_service_broker_unavailable(monkeypatch):
    def raise_broker_error():
        raise OSError("Broker unavailable")
    monkeypatch.setattr(account_service, "get_account", raise_broker_error)
    with pytest.raises(OSError):
        account_service.get_account()

def test_account_service_timeout(monkeypatch):
    def raise_timeout():
        raise TimeoutError("Timeout")
    monkeypatch.setattr(account_service, "get_account", raise_timeout)
    with pytest.raises(TimeoutError):
        account_service.get_account()

def test_account_service_unexpected_exception(monkeypatch):
    def raise_unexpected():
        raise RuntimeError("Unexpected")
    monkeypatch.setattr(account_service, "get_account", raise_unexpected)
    with pytest.raises(RuntimeError):
        account_service.get_account()
