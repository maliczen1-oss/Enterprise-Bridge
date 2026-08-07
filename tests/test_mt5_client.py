"""Unit tests for the real :mod:`core.mt5_client` wrapper.

MetaTrader5 is deliberately absent from the test environment. Every test
executes ``MT5Client`` itself and replaces only the optional SDK binding.
"""

from __future__ import annotations

import datetime
import logging
from unittest.mock import Mock, call

import pytest

from core import mt5_client


class AsDictRecord:
    """Small stand-in for the named tuples returned by the MT5 binding."""

    def __init__(self, **values):
        self.values = values

    def _asdict(self):
        return dict(self.values)


@pytest.fixture(autouse=True)
def bridge_log_level(caplog):
    caplog.set_level(logging.DEBUG, logger="bridge")


@pytest.fixture
def binding(monkeypatch):
    """Install a mocked MetaTrader5 module before constructing a client."""

    sdk = Mock()
    monkeypatch.setattr(mt5_client, "MT5_AVAILABLE", True)
    monkeypatch.setattr(mt5_client, "mt5", sdk)
    monkeypatch.setattr(mt5_client, "PLATFORM", "windows")
    return sdk


def test_get_capabilities_reports_an_enabled_windows_binding(monkeypatch):
    monkeypatch.setattr(mt5_client, "PLATFORM", "windows")
    monkeypatch.setattr(mt5_client, "MT5_AVAILABLE", True)
    monkeypatch.setattr(mt5_client, "mt5", Mock())

    assert mt5_client.get_capabilities() == {
        "platform": "windows",
        "mt5Supported": True,
        "mt5Available": True,
        "backend": "enabled",
    }


@pytest.mark.parametrize("platform_name", ["linux", "darwin", "freebsd"])
def test_get_capabilities_disables_mt5_on_non_windows_platforms(monkeypatch, platform_name):
    monkeypatch.setattr(mt5_client, "PLATFORM", platform_name)
    monkeypatch.setattr(mt5_client, "MT5_AVAILABLE", True)
    monkeypatch.setattr(mt5_client, "mt5", Mock())

    capabilities = mt5_client.get_capabilities()

    assert capabilities["platform"] == platform_name
    assert capabilities["mt5Supported"] is False
    assert capabilities["mt5Available"] is False
    assert capabilities["backend"] == "disabled"


@pytest.mark.parametrize(
    "available, sdk",
    [
        (False, Mock()),
        (True, None),
    ],
)
def test_get_capabilities_disables_the_backend_without_an_available_sdk(
    monkeypatch, available, sdk
):
    monkeypatch.setattr(mt5_client, "PLATFORM", "windows")
    monkeypatch.setattr(mt5_client, "MT5_AVAILABLE", available)
    monkeypatch.setattr(mt5_client, "mt5", sdk)

    assert mt5_client.get_capabilities() == {
        "platform": "windows",
        "mt5Supported": True,
        "mt5Available": False,
        "backend": "disabled",
    }


def test_constructor_retains_the_available_binding_and_starts_uninitialized(binding):
    client = mt5_client.MT5Client()

    assert client._mt5 is binding
    assert client._initialized is False


def test_constructor_uses_no_binding_when_mt5_is_not_importable(monkeypatch):
    monkeypatch.setattr(mt5_client, "MT5_AVAILABLE", False)
    monkeypatch.setattr(mt5_client, "mt5", Mock())

    client = mt5_client.MT5Client()

    assert client._mt5 is None
    assert client._initialized is False


def test_initialize_returns_false_without_the_optional_mt5_package(monkeypatch, caplog):
    sdk = Mock()
    monkeypatch.setattr(mt5_client, "MT5_AVAILABLE", False)
    monkeypatch.setattr(mt5_client, "mt5", sdk)
    client = mt5_client.MT5Client()

    assert client.initialize() is False
    assert client._initialized is False
    sdk.initialize.assert_not_called()
    assert "MT5 initialize called but MT5 is not available" in caplog.text


def test_initialize_without_a_path_delegates_to_the_sdk(binding):
    binding.initialize.return_value = True
    client = mt5_client.MT5Client()

    assert client.initialize() is True
    assert client._initialized is True
    binding.initialize.assert_called_once_with()


def test_initialize_with_a_path_prefers_the_positional_sdk_signature(binding):
    binding.initialize.return_value = True
    client = mt5_client.MT5Client()

    assert client.initialize("C:/MT5/terminal64.exe") is True
    assert client._initialized is True
    binding.initialize.assert_called_once_with("C:/MT5/terminal64.exe")


def test_initialize_falls_back_to_the_keyword_sdk_signature_after_type_error(binding):
    binding.initialize.side_effect = [TypeError("keyword-only"), True]
    client = mt5_client.MT5Client()

    assert client.initialize("C:/MT5/terminal64.exe") is True
    assert client._initialized is True
    assert binding.initialize.call_args_list == [
        call("C:/MT5/terminal64.exe"),
        call(path="C:/MT5/terminal64.exe"),
    ]


@pytest.mark.parametrize("sdk_result", [False, None, 0, ""])
def test_initialize_propagates_a_falsy_sdk_result_as_false(binding, sdk_result):
    binding.initialize.return_value = sdk_result
    client = mt5_client.MT5Client()

    assert client.initialize() is False
    assert client._initialized is False


def test_initialize_contains_sdk_exceptions_and_resets_initialization(binding, caplog):
    binding.initialize.side_effect = RuntimeError("terminal unavailable")
    client = mt5_client.MT5Client()
    client._initialized = True

    assert client.initialize() is False
    assert client._initialized is False
    assert "mt5.initialize() raised: terminal unavailable" in caplog.text


def test_login_returns_false_without_the_optional_mt5_package(monkeypatch, caplog):
    sdk = Mock()
    monkeypatch.setattr(mt5_client, "MT5_AVAILABLE", False)
    monkeypatch.setattr(mt5_client, "mt5", sdk)
    client = mt5_client.MT5Client()

    assert client.login(login=1, password="secret", server="broker") is False
    sdk.initialize.assert_not_called()
    sdk.login.assert_not_called()
    assert "MT5 login called but MT5 is not available" in caplog.text


def test_login_initializes_first_then_accepts_an_existing_terminal_session(binding):
    client = mt5_client.MT5Client()

    assert client.login() is True
    assert client._initialized is True
    binding.initialize.assert_called_once_with()
    binding.login.assert_not_called()


def test_login_does_not_reinitialize_an_initialized_client(binding):
    client = mt5_client.MT5Client()
    client._initialized = True

    assert client.login() is True
    binding.initialize.assert_not_called()
    binding.login.assert_not_called()


def test_login_continues_when_implicit_initialize_raises(binding):
    binding.initialize.side_effect = RuntimeError("already open elsewhere")
    client = mt5_client.MT5Client()

    assert client.login() is True
    assert client._initialized is False
    binding.login.assert_not_called()


def test_login_uses_the_three_argument_sdk_signature_when_server_is_provided(binding):
    binding.login.return_value = True
    client = mt5_client.MT5Client()
    client._initialized = True

    assert client.login(login=123, password="secret", server="Broker-Demo") is True
    binding.login.assert_called_once_with(123, "secret", "Broker-Demo")


def test_login_uses_the_two_argument_sdk_signature_without_a_server(binding):
    binding.login.return_value = True
    client = mt5_client.MT5Client()
    client._initialized = True

    assert client.login(login=123, password="secret") is True
    binding.login.assert_called_once_with(123, "secret")


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (True, True),
        (False, False),
        ((True, "ok"), True),
        ([False, "failed"], False),
        ([], False),
        ({"retcode": 0}, True),
        ({"retcode": 10004}, False),
        ({}, True),
        ("connected", True),
        (0, False),
    ],
)
def test_login_normalizes_supported_sdk_result_shapes(binding, result, expected):
    binding.login.return_value = result
    client = mt5_client.MT5Client()
    client._initialized = True

    assert client.login(login=123, password="secret") is expected


@pytest.mark.parametrize(
    "kwargs",
    [
        {"login": None, "password": "secret"},
        {"login": 123, "password": None},
    ],
)
def test_login_rejects_incomplete_credentials_without_calling_the_sdk(binding, kwargs):
    client = mt5_client.MT5Client()
    client._initialized = True

    assert client.login(**kwargs) is False
    binding.login.assert_not_called()


def test_login_contains_sdk_exceptions(binding, caplog):
    binding.login.side_effect = OSError("network error")
    client = mt5_client.MT5Client()
    client._initialized = True

    assert client.login(login=123, password="secret") is False
    assert "mt5.login() raised: network error" in caplog.text


def test_shutdown_is_a_successful_noop_when_mt5_is_unavailable(monkeypatch):
    monkeypatch.setattr(mt5_client, "MT5_AVAILABLE", False)
    monkeypatch.setattr(mt5_client, "mt5", Mock())
    client = mt5_client.MT5Client()

    assert client.shutdown() is True
    assert client._initialized is False


def test_shutdown_is_a_successful_noop_when_the_binding_is_none(monkeypatch):
    monkeypatch.setattr(mt5_client, "MT5_AVAILABLE", True)
    monkeypatch.setattr(mt5_client, "mt5", None)
    client = mt5_client.MT5Client()

    assert client.shutdown() is True
    assert client._initialized is False


@pytest.mark.parametrize(
    ("sdk_result", "expected"),
    [
        (True, True),
        (False, False),
        (None, True),
        (1, True),
        (0, False),
    ],
)
def test_shutdown_normalizes_the_sdk_result_and_clears_initialization(
    binding, sdk_result, expected
):
    binding.shutdown.return_value = sdk_result
    client = mt5_client.MT5Client()
    client._initialized = True

    assert client.shutdown() is expected
    assert client._initialized is False
    binding.shutdown.assert_called_once_with()


def test_shutdown_contains_sdk_exceptions_and_clears_initialization(binding, caplog):
    binding.shutdown.side_effect = RuntimeError("shutdown failed")
    client = mt5_client.MT5Client()
    client._initialized = True

    assert client.shutdown() is False
    assert client._initialized is False
    assert "mt5.shutdown() raised: shutdown failed" in caplog.text


@pytest.mark.parametrize(
    ("method_name", "binding_method"),
    [
        ("terminal_info", "terminal_info"),
        ("version", "version"),
        ("last_error", "last_error"),
        ("account_info", "account_info"),
        ("positions_get", "positions_get"),
        ("symbols_get", "symbols_get"),
        ("symbol_info", "symbol_info"),
        ("symbol_info_tick", "symbol_info_tick"),
        ("history_deals_get", "history_deals_get"),
        ("history_orders_get", "history_orders_get"),
    ],
)
def test_read_methods_return_safe_defaults_when_mt5_is_unavailable(
    monkeypatch, method_name, binding_method
):
    sdk = Mock()
    monkeypatch.setattr(mt5_client, "MT5_AVAILABLE", False)
    monkeypatch.setattr(mt5_client, "mt5", sdk)
    client = mt5_client.MT5Client()
    from_dt = datetime.datetime(2025, 1, 1)
    to_dt = datetime.datetime(2025, 1, 2)

    if method_name in {"symbol_info", "symbol_info_tick"}:
        result = getattr(client, method_name)("EURUSD")
    elif method_name in {"history_deals_get", "history_orders_get"}:
        result = getattr(client, method_name)(from_dt, to_dt)
    else:
        result = getattr(client, method_name)()

    expected = [] if method_name in {
        "positions_get",
        "symbols_get",
        "history_deals_get",
        "history_orders_get",
    } else None
    assert result == expected
    getattr(sdk, binding_method).assert_not_called()


def test_terminal_info_normalizes_records_and_dictionaries(binding):
    client = mt5_client.MT5Client()
    binding.terminal_info.return_value = AsDictRecord(name="MT5", build=4200)

    assert client.terminal_info() == {"name": "MT5", "build": 4200}

    binding.terminal_info.return_value = {"name": "MT5", "build": 4201}
    assert client.terminal_info() == {"name": "MT5", "build": 4201}


@pytest.mark.parametrize("value", [None, "unexpected", 123])
def test_terminal_info_rejects_unsupported_values(binding, value):
    binding.terminal_info.return_value = value
    client = mt5_client.MT5Client()

    assert client.terminal_info() is None


def test_terminal_info_contains_sdk_exceptions(binding, caplog):
    binding.terminal_info.side_effect = RuntimeError("terminal query failed")
    client = mt5_client.MT5Client()

    assert client.terminal_info() is None
    assert "mt5.terminal_info() raised: terminal query failed" in caplog.text


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ((5, 0, 4200), "(5, 0, 4200)"),
        ("5.0.4200", "5.0.4200"),
        (0, "0"),
        (None, None),
    ],
)
def test_version_returns_the_string_representation_of_sdk_values(binding, value, expected):
    binding.version.return_value = value
    client = mt5_client.MT5Client()

    assert client.version() == expected


def test_version_contains_sdk_exceptions(binding, caplog):
    binding.version.side_effect = RuntimeError("version query failed")
    client = mt5_client.MT5Client()

    assert client.version() is None
    assert "mt5.version() raised: version query failed" in caplog.text


@pytest.mark.parametrize("value", [None, (), [], {"code": 1}, (1, "error")])
def test_last_error_returns_none_only_for_falsy_sdk_values(binding, value):
    binding.last_error.return_value = value
    client = mt5_client.MT5Client()

    expected = value if value else None
    assert client.last_error() == expected


def test_last_error_contains_sdk_exceptions(binding, caplog):
    binding.last_error.side_effect = RuntimeError("error query failed")
    client = mt5_client.MT5Client()

    assert client.last_error() is None
    assert "mt5.last_error() raised: error query failed" in caplog.text


def test_account_info_normalizes_records_and_dictionaries(binding):
    client = mt5_client.MT5Client()
    binding.account_info.return_value = AsDictRecord(login=123456, balance=1000.0)

    assert client.account_info() == {"login": 123456, "balance": 1000.0}

    binding.account_info.return_value = {"login": 123456, "balance": 1001.0}
    assert client.account_info() == {"login": 123456, "balance": 1001.0}


@pytest.mark.parametrize("value", [None, "unexpected", 123])
def test_account_info_rejects_unsupported_values(binding, value):
    binding.account_info.return_value = value
    client = mt5_client.MT5Client()

    assert client.account_info() is None


def test_account_info_contains_sdk_exceptions(binding, caplog):
    binding.account_info.side_effect = RuntimeError("account query failed")
    client = mt5_client.MT5Client()

    assert client.account_info() is None
    assert "mt5.account_info() raised: account query failed" in caplog.text


@pytest.mark.parametrize(
    ("method_name", "binding_method"),
    [
        ("positions_get", "positions_get"),
        ("symbols_get", "symbols_get"),
    ],
)
def test_collection_methods_normalize_records_dicts_and_unrecognized_entries(
    binding, method_name, binding_method
):
    getattr(binding, binding_method).return_value = [
        AsDictRecord(ticket=1, name="EURUSD"),
        {"ticket": 2, "name": "GBPUSD"},
        "not-an-mt5-record",
    ]
    client = mt5_client.MT5Client()

    assert getattr(client, method_name)() == [
        {"ticket": 1, "name": "EURUSD"},
        {"ticket": 2, "name": "GBPUSD"},
        {},
    ]


@pytest.mark.parametrize(
    ("method_name", "binding_method"),
    [
        ("positions_get", "positions_get"),
        ("symbols_get", "symbols_get"),
    ],
)
@pytest.mark.parametrize("sdk_value", [None, [], ()])
def test_collection_methods_return_an_empty_list_for_empty_sdk_values(
    binding, method_name, binding_method, sdk_value
):
    getattr(binding, binding_method).return_value = sdk_value
    client = mt5_client.MT5Client()

    assert getattr(client, method_name)() == []


@pytest.mark.parametrize(
    ("method_name", "binding_method", "log_fragment"),
    [
        ("positions_get", "positions_get", "mt5.positions_get() raised"),
        ("symbols_get", "symbols_get", "mt5.symbols_get() raised"),
    ],
)
def test_collection_methods_contain_sdk_exceptions(
    binding, caplog, method_name, binding_method, log_fragment
):
    getattr(binding, binding_method).side_effect = RuntimeError("collection failed")
    client = mt5_client.MT5Client()

    assert getattr(client, method_name)() == []
    assert log_fragment in caplog.text


@pytest.mark.parametrize(
    ("method_name", "binding_method", "sdk_value", "expected"),
    [
        (
            "symbol_info",
            "symbol_info",
            AsDictRecord(symbol="XAUUSD", bid=2400.0),
            {"symbol": "XAUUSD", "bid": 2400.0},
        ),
        (
            "symbol_info_tick",
            "symbol_info_tick",
            {"symbol": "XAUUSD", "bid": 2400.0},
            {"symbol": "XAUUSD", "bid": 2400.0},
        ),
    ],
)
def test_symbol_methods_pass_the_symbol_and_normalize_results(
    binding, method_name, binding_method, sdk_value, expected
):
    getattr(binding, binding_method).return_value = sdk_value
    client = mt5_client.MT5Client()

    assert getattr(client, method_name)("XAUUSD") == expected
    getattr(binding, binding_method).assert_called_once_with("XAUUSD")


@pytest.mark.parametrize(
    ("method_name", "binding_method", "log_fragment"),
    [
        ("symbol_info", "symbol_info", "mt5.symbol_info(EURUSD) raised"),
        (
            "symbol_info_tick",
            "symbol_info_tick",
            "mt5.symbol_info_tick(EURUSD) raised",
        ),
    ],
)
def test_symbol_methods_contain_sdk_exceptions(
    binding, caplog, method_name, binding_method, log_fragment
):
    getattr(binding, binding_method).side_effect = RuntimeError("symbol query failed")
    client = mt5_client.MT5Client()

    assert getattr(client, method_name)("EURUSD") is None
    assert log_fragment in caplog.text


@pytest.mark.parametrize(
    ("method_name", "binding_method"),
    [
        ("history_deals_get", "history_deals_get"),
        ("history_orders_get", "history_orders_get"),
    ],
)
@pytest.mark.parametrize(
    ("ticket", "symbol"),
    [
        (101, "EURUSD"),
        (None, "EURUSD"),
        (None, None),
    ],
)
def test_history_methods_select_the_correct_sdk_overload(
    binding, method_name, binding_method, ticket, symbol
):
    from_dt = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    to_dt = datetime.datetime(2025, 1, 2, tzinfo=datetime.timezone.utc)
    getattr(binding, binding_method).return_value = [AsDictRecord(ticket=1)]
    client = mt5_client.MT5Client()

    assert getattr(client, method_name)(from_dt, to_dt, ticket=ticket, symbol=symbol) == [
        {"ticket": 1}
    ]

    if ticket is not None:
        getattr(binding, binding_method).assert_called_once_with(from_dt, to_dt, ticket)
    elif symbol:
        getattr(binding, binding_method).assert_called_once_with(from_dt, to_dt, symbol)
    else:
        getattr(binding, binding_method).assert_called_once_with(from_dt, to_dt)


@pytest.mark.parametrize(
    ("method_name", "binding_method"),
    [
        ("history_deals_get", "history_deals_get"),
        ("history_orders_get", "history_orders_get"),
    ],
)
def test_history_methods_prioritize_ticket_over_symbol(binding, method_name, binding_method):
    from_dt = datetime.datetime(2025, 1, 1)
    to_dt = datetime.datetime(2025, 1, 2)
    getattr(binding, binding_method).return_value = []
    client = mt5_client.MT5Client()

    assert getattr(client, method_name)(from_dt, to_dt, ticket=42, symbol="IGNORED") == []
    getattr(binding, binding_method).assert_called_once_with(from_dt, to_dt, 42)


@pytest.mark.parametrize(
    ("method_name", "binding_method"),
    [
        ("history_deals_get", "history_deals_get"),
        ("history_orders_get", "history_orders_get"),
    ],
)
def test_history_methods_normalize_records_dicts_and_unrecognized_entries(
    binding, method_name, binding_method
):
    from_dt = datetime.datetime(2025, 1, 1)
    to_dt = datetime.datetime(2025, 1, 2)
    getattr(binding, binding_method).return_value = [
        AsDictRecord(ticket=1),
        {"ticket": 2},
        "not-an-mt5-record",
    ]
    client = mt5_client.MT5Client()

    assert getattr(client, method_name)(from_dt, to_dt) == [
        {"ticket": 1},
        {"ticket": 2},
        {},
    ]


@pytest.mark.parametrize(
    ("method_name", "binding_method"),
    [
        ("history_deals_get", "history_deals_get"),
        ("history_orders_get", "history_orders_get"),
    ],
)
@pytest.mark.parametrize("sdk_value", [None, [], ()])
def test_history_methods_return_an_empty_list_for_empty_sdk_values(
    binding, method_name, binding_method, sdk_value
):
    from_dt = datetime.datetime(2025, 1, 1)
    to_dt = datetime.datetime(2025, 1, 2)
    getattr(binding, binding_method).return_value = sdk_value
    client = mt5_client.MT5Client()

    assert getattr(client, method_name)(from_dt, to_dt) == []


@pytest.mark.parametrize(
    ("method_name", "binding_method", "log_fragment"),
    [
        ("history_deals_get", "history_deals_get", "mt5.history_deals_get() raised"),
        ("history_orders_get", "history_orders_get", "mt5.history_orders_get() raised"),
    ],
)
def test_history_methods_contain_sdk_exceptions(
    binding, caplog, method_name, binding_method, log_fragment
):
    from_dt = datetime.datetime(2025, 1, 1)
    to_dt = datetime.datetime(2025, 1, 2)
    getattr(binding, binding_method).side_effect = RuntimeError("history query failed")
    client = mt5_client.MT5Client()

    assert getattr(client, method_name)(from_dt, to_dt) == []
    assert log_fragment in caplog.text
