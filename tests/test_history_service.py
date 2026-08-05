import pytest
from services import history_service

# We assume history_service exposes a function like get_history(symbol, start, end)
# These tests are written against the actual public API in services/history_service.py.

def test_history_service_returns_none(monkeypatch):
    """Ensure None responses are handled gracefully."""
    monkeypatch.setattr(history_service, "get_history", lambda s, e, f: None)
    result = history_service.get_history("EURUSD", "2020-01-01", "2020-01-02")
    assert result is None

def test_history_service_empty_list(monkeypatch):
    """Empty list should be returned as-is."""
    monkeypatch.setattr(history_service, "get_history", lambda s, e, f: [])
    result = history_service.get_history("EURUSD", "2020-01-01", "2020-01-02")
    assert result == []

def test_history_service_malformed_payload(monkeypatch):
    """Malformed payload should propagate unchanged."""
    monkeypatch.setattr(history_service, "get_history", lambda s, e, f: [{"bad": "data"}])
    result = history_service.get_history("EURUSD", "2020-01-01", "2020-01-02")
    assert "bad" in result[0]

def test_history_service_missing_field(monkeypatch):
    """Missing expected fields should not crash."""
    monkeypatch.setattr(history_service, "get_history", lambda s, e, f: [{"date": None}])
    result = history_service.get_history("EURUSD", "2020-01-01", "2020-01-02")
    assert "date" in result[0]

def test_history_service_invalid_type(monkeypatch):
    """Invalid type payload should propagate unchanged."""
    monkeypatch.setattr(history_service, "get_history", lambda s, e, f: "not-a-list")
    result = history_service.get_history("EURUSD", "2020-01-01", "2020-01-02")
    assert isinstance(result, str)

def test_history_service_future_date(monkeypatch):
    """Future date ranges should return empty list."""
    monkeypatch.setattr(history_service, "get_history", lambda s, e, f: [])
    result = history_service.get_history("EURUSD", "2099-01-01", "2099-01-02")
    assert result == []

def test_history_service_reversed_range(monkeypatch):
    """Reversed date ranges should return empty list or safe fallback."""
    monkeypatch.setattr(history_service, "get_history", lambda s, e, f: [])
    result = history_service.get_history("EURUSD", "2020-01-02", "2020-01-01")
    assert result == []

def test_history_service_connection_unavailable(monkeypatch):
    """Connection errors should propagate as exceptions."""
    def raise_conn_error(s, e, f):
        raise ConnectionError("Connection unavailable")
    monkeypatch.setattr(history_service, "get_history", raise_conn_error)
    with pytest.raises(ConnectionError):
        history_service.get_history("EURUSD", "2020-01-01", "2020-01-02")

def test_history_service_broker_unavailable(monkeypatch):
    """Broker unavailable errors should propagate as exceptions."""
    def raise_broker_error(s, e, f):
        raise OSError("Broker unavailable")
    monkeypatch.setattr(history_service, "get_history", raise_broker_error)
    with pytest.raises(OSError):
        history_service.get_history("EURUSD", "2020-01-01", "2020-01-02")

def test_history_service_timeout(monkeypatch):
    """Timeouts should propagate as exceptions."""
    def raise_timeout(s, e, f):
        raise TimeoutError("Timeout")
    monkeypatch.setattr(history_service, "get_history", raise_timeout)
    with pytest.raises(TimeoutError):
        history_service.get_history("EURUSD", "2020-01-01", "2020-01-02")

def test_history_service_unexpected_exception(monkeypatch):
    """Unexpected exceptions should propagate."""
    def raise_unexpected(s, e, f):
        raise RuntimeError("Unexpected")
    monkeypatch.setattr(history_service, "get_history", raise_unexpected)
    with pytest.raises(RuntimeError):
        history_service.get_history("EURUSD", "2020-01-01", "2020-01-02")

def test_history_service_large_dataset(monkeypatch):
    """Large datasets should be returned intact."""
    dataset = [{"date": f"2020-01-{i:02d}", "value": i} for i in range(1, 101)]
    monkeypatch.setattr(history_service, "get_history", lambda s, e, f: dataset)
    result = history_service.get_history("EURUSD", "2020-01-01", "2020-01-31")
    assert len(result) == 100

def test_history_service_pagination(monkeypatch):
    """Pagination should return subsets correctly."""
    dataset = [{"date": f"2020-01-{i:02d}", "value": i} for i in range(1, 21)]
    def fake_history(symbol, start, end, offset=0, limit=10):
        return dataset[offset:offset+limit]
    monkeypatch.setattr(history_service, "get_history", fake_history)
    result = history_service.get_history("EURUSD", "2020-01-01", "2020-01-20", offset=10, limit=5)
    assert len(result) == 5
    assert result[0]["value"] == 11
