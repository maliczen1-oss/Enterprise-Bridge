import pytest
from services.mt5_client import MT5Client

class DummyMT5:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc

    def initialize(self):
        if self.exc:
            raise self.exc
        return True

    def login(self, login, password, server):
        if self.exc:
            raise self.exc
        if login == "bad":
            raise ValueError("Invalid credentials")
        return True

    def shutdown(self):
        if self.exc:
            raise self.exc
        return True

    def symbols_get(self):
        if self.exc:
            raise self.exc
        return self.response

    def history_get(self, *args, **kwargs):
        if self.exc:
            raise self.exc
        return self.response

    def account_info(self):
        if self.exc:
            raise self.exc
        return self.response

    def positions_get(self):
        if self.exc:
            raise self.exc
        return self.response


@pytest.fixture
def client():
    return MT5Client(mt5=DummyMT5())


def test_initialize_success(client):
    assert client.initialize() is True


def test_initialize_missing_dll():
    client = MT5Client(mt5=DummyMT5(exc=FileNotFoundError("DLL missing")))
    with pytest.raises(FileNotFoundError):
        client.initialize()


def test_initialize_unsupported_os():
    client = MT5Client(mt5=DummyMT5(exc=OSError("Unsupported OS")))
    with pytest.raises(OSError):
        client.initialize()


def test_login_success(client):
    assert client.login("user", "pass", "server") is True


def test_login_invalid_credentials():
    client = MT5Client(mt5=DummyMT5())
    with pytest.raises(ValueError):
        client.login("bad", "pass", "server")


def test_login_broker_unavailable():
    client = MT5Client(mt5=DummyMT5(exc=ConnectionError("Broker unavailable")))
    with pytest.raises(ConnectionError):
        client.login("user", "pass", "server")


def test_shutdown_success(client):
    assert client.shutdown() is True


def test_shutdown_unexpected_exception():
    client = MT5Client(mt5=DummyMT5(exc=RuntimeError("Unexpected")))
    with pytest.raises(RuntimeError):
        client.shutdown()


def test_symbol_retrieval(client):
    client.mt5.response = [{"name": "EURUSD"}]
    result = client.symbols_get()
    assert result[0]["name"] == "EURUSD"


def test_symbol_retrieval_timeout():
    client = MT5Client(mt5=DummyMT5(exc=TimeoutError("Timeout")))
    with pytest.raises(TimeoutError):
        client.symbols_get()


def test_history_retrieval(client):
    client.mt5.response = [{"date": "2020-01-01"}]
    result = client.history_get("EURUSD", "2020-01-01", "2020-01-02")
    assert result[0]["date"] == "2020-01-01"


def test_history_retrieval_future_date(client):
    client.mt5.response = []
    result = client.history_get("EURUSD", "2099-01-01", "2099-01-02")
    assert result == []


def test_account_retrieval(client):
    client.mt5.response = {"balance": 1000}
    result = client.account_info()
    assert result["balance"] == 1000


def test_account_retrieval_none(client):
    client.mt5.response = None
    result = client.account_info()
    assert result is None


def test_positions_retrieval(client):
    client.mt5.response = [{"ticket": 123}]
    result = client.positions_get()
    assert result[0]["ticket"] == 123


def test_positions_retrieval_broker_unavailable():
    client = MT5Client(mt5=DummyMT5(exc=OSError("Broker unavailable")))
    with pytest.raises(OSError):
        client.positions_get()


def test_reconnect_success(client):
    client.mt5.response = True
    assert client.reconnect() is True


def test_reconnect_failure():
    client = MT5Client(mt5=DummyMT5(exc=RuntimeError("Reconnect failed")))
    with pytest.raises(RuntimeError):
        client.reconnect()
