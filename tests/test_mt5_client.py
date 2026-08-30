from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import httpx
import pytest

from core import mt5_client


def metaapi_client(monkeypatch):
    monkeypatch.setattr(mt5_client, "METAAPI_TOKEN", "token-value")
    monkeypatch.setattr(mt5_client, "METAAPI_ACCOUNT_ID", "account-id")
    monkeypatch.setattr(mt5_client, "METAAPI_CONFIGURED", True)
    client = mt5_client.MT5Client()
    assert client.backend == "metaapi"
    return client


def test_capabilities_select_metaapi_when_configured(monkeypatch):
    monkeypatch.setattr(mt5_client, "METAAPI_CONFIGURED", True)
    monkeypatch.setattr(mt5_client, "METAAPI_TOKEN", "configured")
    monkeypatch.setattr(mt5_client, "METAAPI_ACCOUNT_ID", "configured")
    caps = mt5_client.get_capabilities()
    assert caps["backend"] == "metaapi"
    assert caps["mt5Supported"] is True
    assert caps["mt5Available"] is True


def test_capabilities_disable_unavailable_backend(monkeypatch):
    monkeypatch.setattr(mt5_client, "METAAPI_CONFIGURED", False)
    monkeypatch.setattr(mt5_client, "METAAPI_TOKEN", "")
    monkeypatch.setattr(mt5_client, "METAAPI_ACCOUNT_ID", "")
    monkeypatch.setattr(mt5_client, "_LOCAL_MT5_AVAILABLE", False)
    assert mt5_client.get_capabilities()["backend"] == "disabled"


def test_disabled_backend_fails_closed(monkeypatch):
    monkeypatch.setattr(mt5_client, "METAAPI_CONFIGURED", False)
    monkeypatch.setattr(mt5_client, "_LOCAL_MT5_AVAILABLE", False)
    client = mt5_client.MT5Client()
    assert client.initialize() is False
    assert client.login() is False
    assert client.account_info() is None
    assert client.positions_get() == []
    assert client.symbols_get() == []


def test_error_details_drop_credentials(monkeypatch):
    client = metaapi_client(monkeypatch)
    client._set_error(
        "FAIL",
        "safe",
        details={"token": "secret", "authorization": "secret", "host": "example"},
    )
    error = client.last_error()
    assert error["details"] == {"host": "example"}
    assert "secret" not in str(error)


@pytest.mark.parametrize("value,expected", [("2.5", 2.5), ("0", 1.0), ("bad", 1.0)])
def test_env_float_is_bounded_to_positive_values(monkeypatch, value, expected):
    monkeypatch.setenv("TEST_FLOAT", value)
    assert mt5_client._env_float("TEST_FLOAT", 1.0) == expected


def test_initialize_and_login_metaapi(monkeypatch):
    client = metaapi_client(monkeypatch)
    metadata = {"state": "DEPLOYED", "connectionStatus": "CONNECTED", "region": "london"}
    monkeypatch.setattr(client, "_refresh_account_metadata", lambda: metadata)
    monkeypatch.setattr(client, "_metaapi_get", lambda path, params=None: {"balance": 100})
    assert client.initialize() is True
    assert client.initialized is True
    assert client.login() is True
    assert client.last_error() is None


def test_metaapi_not_connected_fails_readiness(monkeypatch):
    client = metaapi_client(monkeypatch)
    metadata = {"state": "DEPLOYED", "connectionStatus": "DISCONNECTED", "region": "london"}
    monkeypatch.setattr(client, "_refresh_account_metadata", lambda: metadata)
    assert client.initialize() is True
    assert client.login() is False
    assert client.last_error()["code"] == "METAAPI_ACCOUNT_NOT_CONNECTED"


def test_metaapi_read_methods_normalize_shapes(monkeypatch):
    client = metaapi_client(monkeypatch)

    def get(path, params=None):
        if path.endswith("account-information"):
            return {"balance": 10}
        if path.endswith("/positions"):
            return [{"id": "1"}, "bad"]
        if path.endswith("/symbols"):
            return ["EURUSD", "", 5]
        if path.endswith("/specification"):
            return {"digits": 5}
        if path.endswith("/current-tick"):
            return {"bid": 1.1}
        raise AssertionError(path)

    monkeypatch.setattr(client, "_metaapi_get", get)
    assert client.account_info() == {"balance": 10}
    assert client.positions_get() == [{"id": "1"}]
    assert client.symbols_get() == [{"name": "EURUSD", "symbol": "EURUSD"}]
    assert client.symbol_info("EUR/USD")["symbol"] == "EUR/USD"
    assert client.symbol_info_tick("EUR/USD")["symbol"] == "EUR/USD"


@pytest.mark.parametrize("method", ["symbol_info", "symbol_info_tick"])
def test_symbol_reads_reject_blank_symbol(monkeypatch, method):
    client = metaapi_client(monkeypatch)
    assert getattr(client, method)(" ") is None
    assert client.last_error()["code"] == "INVALID_SYMBOL"


def test_history_reads_filter_symbol_and_use_utc_paths(monkeypatch):
    client = metaapi_client(monkeypatch)
    calls = []

    def get(path, params=None):
        calls.append((path, params))
        return [{"id": "1", "symbol": "EURUSD"}, {"id": "2", "symbol": "GBPUSD"}, "bad"]

    monkeypatch.setattr(client, "_metaapi_get", get)
    start = dt.datetime(2026, 1, 1)
    end = dt.datetime(2026, 1, 2, tzinfo=dt.timezone.utc)
    assert client.history_deals_get(start, end, symbol="eurusd") == [{"id": "1", "symbol": "EURUSD"}]
    assert client.history_orders_get(start, end, symbol="eurusd") == [{"id": "1", "symbol": "EURUSD"}]
    assert all("time" in path and "%3A" in path for path, _ in calls)
    assert all(params == {"limit": 1000, "offset": 0} for _, params in calls)


def test_shutdown_closes_metaapi_client(monkeypatch):
    client = metaapi_client(monkeypatch)
    transport = SimpleNamespace(closed=False)
    transport.close = lambda: setattr(transport, "closed", True)
    client._http = transport
    client._initialized = True
    assert client.shutdown() is True
    assert transport.closed is True
    assert client.initialized is False
    assert client._http is None


def test_request_retries_timeout_without_leaking_credentials(monkeypatch):
    client = metaapi_client(monkeypatch)
    client._retry_count = 1
    client._retry_delay = 0.01
    attempts = []

    class FailingHttp:
        def request(self, *args, **kwargs):
            attempts.append(1)
            raise httpx.ReadTimeout("token-value account-id")

    monkeypatch.setattr(client, "_ensure_http_client", lambda: FailingHttp())
    monkeypatch.setattr(mt5_client.time, "sleep", lambda delay: None)
    monkeypatch.setattr(mt5_client, "_resolve_hostname", lambda *args: {"resolved": False, "addresses": []})
    with pytest.raises(mt5_client.MetaApiError):
        client._request_metaapi("GET", "https://example.invalid/path")
    assert len(attempts) == 2
    assert "token-value" not in str(client.last_error())
    assert "account-id" not in str(client.last_error())


def test_legacy_backend_delegates_and_converts_records(monkeypatch):
    record = SimpleNamespace(_asdict=lambda: {"ticket": 1})
    fake = SimpleNamespace(
        initialize=lambda *args, **kwargs: True,
        login=lambda *args: True,
        shutdown=lambda: None,
        account_info=lambda: record,
        positions_get=lambda: [record],
        symbols_get=lambda: [record],
        symbol_info=lambda symbol: record,
        symbol_info_tick=lambda symbol: record,
        symbol_select=lambda symbol, selected: True,
        copy_rates_from_pos=lambda *args: [record],
        TIMEFRAME_H1=16385,
        history_deals_get=lambda *args: [record],
        history_orders_get=lambda *args: [record],
        terminal_info=lambda: record,
        version=lambda: (5, 0, 1),
        last_error=lambda: (0, "ok"),
    )
    monkeypatch.setattr(mt5_client, "METAAPI_CONFIGURED", False)
    monkeypatch.setattr(mt5_client, "_LOCAL_MT5_AVAILABLE", True)
    monkeypatch.setattr(mt5_client, "PLATFORM", "windows")
    monkeypatch.setattr(mt5_client, "mt5", fake)
    client = mt5_client.MT5Client()
    assert client.initialize() is True
    assert client.login(1, "password", "server") is True
    assert client.account_info() == {"ticket": 1}
    assert client.positions_get() == [{"ticket": 1}]
    assert client.symbols_get() == [{"ticket": 1}]
    assert client.copy_rates_from_pos("EURUSD", "H1", count=10) == [{"ticket": 1}]
    assert client.history_deals_get(*[dt.datetime.now()] * 2) == [{"ticket": 1}]
    assert client.shutdown() is True


def test_market_bars_reject_invalid_arguments(monkeypatch):
    client = metaapi_client(monkeypatch)
    assert client.copy_rates_from_pos("", "H1") == []
    assert client.last_error()["code"] == "INVALID_SYMBOL"
    assert client.copy_rates_from_pos("EURUSD", "H2") == []
    assert client.last_error()["code"] == "INVALID_TIMEFRAME"
    assert client.copy_rates_from_pos("EURUSD", "H1", count=2001) == []
    assert client.last_error()["code"] == "INVALID_BAR_COUNT"


def test_metaapi_market_bars_fail_closed(monkeypatch):
    client = metaapi_client(monkeypatch)
    assert client.copy_rates_from_pos("EURUSD", "H1") == []
    assert client.last_error()["code"] == "MARKET_BARS_UNSUPPORTED"


def test_legacy_market_bars_fail_when_symbol_cannot_be_selected(monkeypatch):
    fake = SimpleNamespace(
        TIMEFRAME_H1=16385,
        symbol_select=lambda symbol, selected: False,
        copy_rates_from_pos=lambda *args: pytest.fail("bars must not be read"),
    )
    monkeypatch.setattr(mt5_client, "METAAPI_CONFIGURED", False)
    monkeypatch.setattr(mt5_client, "_LOCAL_MT5_AVAILABLE", True)
    monkeypatch.setattr(mt5_client, "PLATFORM", "windows")
    monkeypatch.setattr(mt5_client, "mt5", fake)
    client = mt5_client.MT5Client()
    client._backend = "metatrader5"
    client._mt5 = fake
    assert client.copy_rates_from_pos("XAUUSD.mic", "H1", count=10) == []
    assert client.last_error()["code"] == "SYMBOL_UNAVAILABLE"
