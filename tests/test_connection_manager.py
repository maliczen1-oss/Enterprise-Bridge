"""Integration-style unit tests for :mod:`core.connection_manager`.

The manager owns the state machine and worker loop. These tests deliberately
exercise that implementation; only its external boundaries (the MT5 wrapper,
settings, time/random, and worker-thread primitive) are replaced.
"""

from __future__ import annotations

import datetime
import logging
import threading
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from core import connection_manager as connection_manager_module


ConnectionManager = connection_manager_module.ConnectionManager
ConnectionState = connection_manager_module.ConnectionState


DEFAULT_CAPABILITIES = {
    "platform": "windows",
    "mt5Supported": True,
    "mt5Available": True,
    "backend": "enabled",
}

DEFAULT_SETTINGS = {
    "MT5_RETRY_BASE_DELAY": 2.0,
    "MT5_RETRY_MAX_DELAY": 30.0,
    "MT5_MAX_RETRIES": 3,
    "MT5_CONNECTION_TIMEOUT": 15_000,
    "MT5_TERMINAL_PATH": "C:/Program Files/MetaTrader 5/terminal64.exe",
    "MT5_LOGIN": 123456,
    "MT5_PASSWORD": "test-password",
    "MT5_SERVER": "TestBroker-Demo",
}


class FakeMT5Client:
    """A controllable stand-in for the MT5 boundary used by the manager."""

    def __init__(
        self,
        *,
        initialize_result=True,
        login_result=True,
        shutdown_result=True,
        last_error_result=None,
        terminal_info_result=None,
        version_result="5.0.0",
    ):
        self.initialize_result = initialize_result
        self.initialize_outcomes = []
        self.login_result = login_result
        self.login_outcomes = []
        self.shutdown_result = shutdown_result
        self.shutdown_outcomes = []
        self.last_error_result = last_error_result
        self.terminal_info_result = terminal_info_result
        self.version_result = version_result

        self.account_result = {"login": 123456}
        self.positions_result = [{"ticket": 10}]
        self.symbols_result = [{"name": "EURUSD"}]
        self.symbol_info_result = {"name": "EURUSD", "digits": 5}
        self.symbol_tick_result = {"bid": 1.1, "ask": 1.1001}
        self.history_deals_result = [{"ticket": 100}]
        self.history_orders_result = [{"ticket": 200}]

        self.initialize_calls = []
        self.login_calls = []
        self.shutdown_calls = 0
        self.last_error_calls = 0
        self.terminal_info_calls = 0
        self.version_calls = 0
        self.account_calls = 0
        self.positions_calls = 0
        self.symbols_calls = 0
        self.symbol_info_calls = []
        self.symbol_tick_calls = []
        self.history_deals_calls = []
        self.history_orders_calls = []

    @staticmethod
    def _resolve(value):
        if isinstance(value, BaseException):
            raise value
        if callable(value):
            return value()
        return value

    @staticmethod
    def _next(outcomes, fallback):
        return outcomes.pop(0) if outcomes else fallback

    def initialize(self, path=None):
        self.initialize_calls.append(path)
        return self._resolve(self._next(self.initialize_outcomes, self.initialize_result))

    def login(self, login=None, password=None, server=None):
        self.login_calls.append((login, password, server))
        return self._resolve(self._next(self.login_outcomes, self.login_result))

    def shutdown(self):
        self.shutdown_calls += 1
        return self._resolve(self._next(self.shutdown_outcomes, self.shutdown_result))

    def last_error(self):
        self.last_error_calls += 1
        return self._resolve(self.last_error_result)

    def terminal_info(self):
        self.terminal_info_calls += 1
        return self._resolve(self.terminal_info_result)

    def version(self):
        self.version_calls += 1
        return self._resolve(self.version_result)

    def account_info(self):
        self.account_calls += 1
        return self._resolve(self.account_result)

    def positions_get(self):
        self.positions_calls += 1
        return self._resolve(self.positions_result)

    def symbols_get(self):
        self.symbols_calls += 1
        return self._resolve(self.symbols_result)

    def symbol_info(self, symbol):
        self.symbol_info_calls.append(symbol)
        return self._resolve(self.symbol_info_result)

    def symbol_info_tick(self, symbol):
        self.symbol_tick_calls.append(symbol)
        return self._resolve(self.symbol_tick_result)

    def history_deals_get(self, from_dt, to_dt, ticket=None, symbol=None):
        self.history_deals_calls.append((from_dt, to_dt, ticket, symbol))
        return self._resolve(self.history_deals_result)

    def history_orders_get(self, from_dt, to_dt, ticket=None, symbol=None):
        self.history_orders_calls.append((from_dt, to_dt, ticket, symbol))
        return self._resolve(self.history_orders_result)


class RecordingThread:
    """Thread substitute used when testing lifecycle orchestration only."""

    instances = []
    finish_on_join = True

    def __init__(self, *, target, name, daemon):
        self.target = target
        self.name = name
        self.daemon = daemon
        self.started = False
        self.alive = False
        self.join_timeouts = []
        type(self).instances.append(self)

    def start(self):
        self.started = True
        self.alive = True

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        self.join_timeouts.append(timeout)
        if type(self).finish_on_join:
            self.alive = False


class ExistingWorker:
    """A worker already owned by a manager when ``stop`` is called."""

    def __init__(self, *, alive=True, finish_on_join=True):
        self.alive = alive
        self.finish_on_join = finish_on_join
        self.join_timeouts = []

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        self.join_timeouts.append(timeout)
        if self.finish_on_join:
            self.alive = False


class ScriptedStopEvent:
    """Deterministically drives a direct invocation of the worker loop."""

    def __init__(self, values, *, default=True):
        self._values = iter(values)
        self.default = default
        self.set_calls = 0
        self.clear_calls = 0

    def is_set(self):
        return next(self._values, self.default)

    def set(self):
        self.set_calls += 1

    def clear(self):
        self.clear_calls += 1


@pytest.fixture(autouse=True)
def bridge_log_level(caplog):
    caplog.set_level(logging.DEBUG, logger="bridge")


@pytest.fixture
def manager_factory(monkeypatch):
    """Create a manager with only its external dependencies replaced."""

    def create(*, capabilities=None, settings_values=None, client=None):
        capabilities = dict(DEFAULT_CAPABILITIES if capabilities is None else capabilities)
        setting_values = (
            dict(DEFAULT_SETTINGS) if settings_values is None else dict(settings_values)
        )
        client = client or FakeMT5Client()

        monkeypatch.setattr(
            connection_manager_module.mt5_client,
            "MT5Client",
            lambda: client,
        )
        monkeypatch.setattr(
            connection_manager_module.mt5_client,
            "get_capabilities",
            lambda: dict(capabilities),
        )
        monkeypatch.setattr(
            connection_manager_module,
            "settings",
            SimpleNamespace(**setting_values),
        )
        return ConnectionManager(), client

    return create


@pytest.fixture
def ready_manager(manager_factory):
    def create(**kwargs):
        manager, client = manager_factory(**kwargs)
        assert manager._attempt_initialize_and_connect() is True
        assert manager.is_connected() is True
        return manager, client

    return create


def test_constructor_marks_an_unsupported_platform_and_retains_capabilities(
    manager_factory, caplog
):
    manager, _ = manager_factory(
        capabilities={
            "platform": "linux",
            "mt5Supported": False,
            "mt5Available": False,
            "backend": "disabled",
        }
    )

    assert manager.get_state() == ConnectionState.UNSUPPORTED_PLATFORM.value
    assert manager.is_connected() is False
    assert manager.get_capabilities() == {
        "platform": "linux",
        "mt5Supported": False,
        "mt5Available": False,
        "backend": "disabled",
        "state": "UNSUPPORTED_PLATFORM",
        "mt5Initialized": False,
        "terminalVersion": None,
        "lastError": None,
    }
    assert "Platform does not support MT5" in caplog.text


def test_constructor_marks_a_missing_mt5_backend_unavailable(manager_factory, caplog):
    manager, _ = manager_factory(
        capabilities={
            "platform": "windows",
            "mt5Supported": True,
            "mt5Available": False,
            "backend": "disabled",
        }
    )

    assert manager.get_state() == ConnectionState.BACKEND_UNAVAILABLE.value
    assert manager.get_health()["connectionState"] == "BACKEND_UNAVAILABLE"
    assert "MT5 package not available" in caplog.text


def test_constructor_loads_the_client_capabilities_and_retry_settings(manager_factory):
    manager, client = manager_factory()

    assert isinstance(manager._client, FakeMT5Client)
    assert manager._client is client
    assert manager.get_state() == ConnectionState.DISCONNECTED.value
    assert manager._base_retry_delay == 2.0
    assert manager._max_retry_delay == 30.0
    assert manager._max_retries == 3
    assert manager._connection_timeout == 15_000
    assert manager._reconnect_count == 0
    assert manager._last_reconnect_time is None


def test_constructor_uses_documented_retry_and_timeout_fallbacks(manager_factory):
    manager, _ = manager_factory(settings_values={"MT5_TIMEOUT": 8_000})

    assert manager._base_retry_delay == 1.0
    assert manager._max_retry_delay == 60.0
    assert manager._max_retries == 10
    assert manager._connection_timeout == 8_000


@pytest.mark.parametrize(
    ("previous", "next_state"),
    [
        (ConnectionState.DISCONNECTED, ConnectionState.INITIALIZING),
        (ConnectionState.DISCONNECTED, ConnectionState.SHUTTING_DOWN),
        (ConnectionState.DISCONNECTED, ConnectionState.UNSUPPORTED_PLATFORM),
        (ConnectionState.DISCONNECTED, ConnectionState.BACKEND_UNAVAILABLE),
        (ConnectionState.INITIALIZING, ConnectionState.CONNECTING),
        (ConnectionState.INITIALIZING, ConnectionState.FAILED),
        (ConnectionState.INITIALIZING, ConnectionState.SHUTTING_DOWN),
        (ConnectionState.CONNECTING, ConnectionState.CONNECTED),
        (ConnectionState.CONNECTING, ConnectionState.FAILED),
        (ConnectionState.CONNECTING, ConnectionState.SHUTTING_DOWN),
        (ConnectionState.CONNECTED, ConnectionState.SHUTTING_DOWN),
        (ConnectionState.CONNECTED, ConnectionState.DISCONNECTED),
        (ConnectionState.CONNECTED, ConnectionState.FAILED),
        (ConnectionState.FAILED, ConnectionState.INITIALIZING),
        (ConnectionState.FAILED, ConnectionState.SHUTTING_DOWN),
        (ConnectionState.FAILED, ConnectionState.DISCONNECTED),
        (ConnectionState.SHUTTING_DOWN, ConnectionState.DISCONNECTED),
        (ConnectionState.UNSUPPORTED_PLATFORM, ConnectionState.DISCONNECTED),
        (ConnectionState.BACKEND_UNAVAILABLE, ConnectionState.INITIALIZING),
        (ConnectionState.BACKEND_UNAVAILABLE, ConnectionState.DISCONNECTED),
    ],
)
def test_declared_legal_state_transitions_are_accepted(
    manager_factory, previous, next_state
):
    manager, _ = manager_factory()

    assert manager._is_legal_transition(previous, next_state) is True


def test_set_state_applies_legal_transitions_and_rejects_illegal_ones(
    manager_factory, caplog
):
    manager, _ = manager_factory()

    manager._set_state(ConnectionState.INITIALIZING)
    assert manager.get_state() == ConnectionState.INITIALIZING.value

    manager._set_state(ConnectionState.CONNECTED)
    assert manager.get_state() == ConnectionState.INITIALIZING.value
    assert "Illegal state transition attempted from INITIALIZING to CONNECTED" in caplog.text


def test_successful_connection_uses_settings_and_collects_terminal_details(
    manager_factory, caplog
):
    client = FakeMT5Client(
        terminal_info_result={"name": "MetaTrader 5"}, version_result=(5, 0, 4200)
    )
    manager, client = manager_factory(client=client)

    assert manager._attempt_initialize_and_connect() is True

    assert client.initialize_calls == [DEFAULT_SETTINGS["MT5_TERMINAL_PATH"]]
    assert client.login_calls == [
        (
            DEFAULT_SETTINGS["MT5_LOGIN"],
            DEFAULT_SETTINGS["MT5_PASSWORD"],
            DEFAULT_SETTINGS["MT5_SERVER"],
        )
    ]
    assert manager.get_state() == ConnectionState.CONNECTED.value
    assert manager.is_connected() is True
    assert manager._mt5_initialized is True
    assert manager.get_terminal_info() == {"name": "MetaTrader 5"}
    assert manager.get_version() == "(5, 0, 4200)"
    assert manager.get_last_error() is None
    assert "Attempting MT5 initialize" in caplog.text
    assert "Connected to MT5" in caplog.text


def test_initialize_false_records_mt5_error_and_keeps_manager_uninitialized(manager_factory):
    client = FakeMT5Client(
        initialize_result=False, last_error_result={"code": -1, "message": "missing"}
    )
    manager, client = manager_factory(client=client)

    assert manager._attempt_initialize_and_connect() is False

    assert client.login_calls == []
    assert manager._mt5_initialized is False
    assert manager.get_state() == ConnectionState.DISCONNECTED.value
    assert manager.get_last_error()["code"] == "MT5_INITIALIZE_FAILED"
    assert "mt5.initialize() returned False" in manager.get_last_error()["message"]
    assert "missing" in manager.get_last_error()["message"]


def test_initialize_exception_is_contained_and_reported(manager_factory, caplog):
    client = FakeMT5Client(
        initialize_result=RuntimeError("terminal process failed"),
        last_error_result={"code": 1001},
    )
    manager, _ = manager_factory(client=client)

    assert manager._attempt_initialize_and_connect() is False

    error = manager.get_last_error()
    assert error["code"] == "MT5_INITIALIZE_FAILED"
    assert "1001" in error["message"]
    assert "MT5_INITIALIZE_EXCEPTION" in caplog.text


def test_login_failure_records_error_and_moves_to_failed_state(manager_factory):
    client = FakeMT5Client(login_result=False, last_error_result={"code": 401})
    manager, _ = manager_factory(client=client)

    assert manager._attempt_initialize_and_connect() is False

    assert manager._mt5_initialized is True
    assert manager.get_state() == ConnectionState.FAILED.value
    assert manager.get_last_error()["code"] == "MT5_LOGIN_FAILED"
    assert "401" in manager.get_last_error()["message"]


def test_login_exception_is_not_exposed_to_callers(manager_factory):
    client = FakeMT5Client(
        login_result=ConnectionError("broker socket closed"),
        last_error_result={"reason": "offline"},
    )
    manager, _ = manager_factory(client=client)

    assert manager._attempt_initialize_and_connect() is False

    assert manager.get_state() == ConnectionState.FAILED.value
    assert manager.get_last_error()["code"] == "MT5_LOGIN_FAILED"
    assert "offline" in manager.get_last_error()["message"]


def test_terminal_metadata_failures_do_not_prevent_a_connection(manager_factory):
    client = FakeMT5Client(
        terminal_info_result=RuntimeError("no terminal info"),
        version_result=RuntimeError("no version"),
    )
    manager, _ = manager_factory(client=client)

    assert manager._attempt_initialize_and_connect() is True

    assert manager.get_state() == ConnectionState.CONNECTED.value
    assert manager.get_terminal_info() is None
    assert manager.get_version() is None


def test_start_creates_and_starts_a_named_daemon_worker(manager_factory, monkeypatch):
    RecordingThread.instances.clear()
    RecordingThread.finish_on_join = True
    monkeypatch.setattr(connection_manager_module.threading, "Thread", RecordingThread)
    manager, _ = manager_factory()

    manager.start()

    assert len(RecordingThread.instances) == 1
    worker = RecordingThread.instances[0]
    assert worker.target == manager._run
    assert worker.name == "mt5-connection-worker"
    assert worker.daemon is True
    assert worker.started is True
    assert manager._stop_event.is_set() is False


def test_start_is_idempotent_when_its_worker_is_alive(manager_factory, monkeypatch, caplog):
    RecordingThread.instances.clear()
    monkeypatch.setattr(connection_manager_module.threading, "Thread", RecordingThread)
    manager, _ = manager_factory()

    manager.start()
    manager.start()

    assert len(RecordingThread.instances) == 1
    assert "Start called but worker thread already running" in caplog.text


@pytest.mark.parametrize(
    "capabilities, expected_message",
    [
        (
            {"mt5Supported": False, "mt5Available": False},
            "Start called but platform does not support MT5",
        ),
        (
            {"mt5Supported": True, "mt5Available": False},
            "Start called but MT5 backend not available",
        ),
    ],
)
def test_start_does_not_spawn_a_worker_when_the_runtime_cannot_use_mt5(
    manager_factory, monkeypatch, caplog, capabilities, expected_message
):
    def thread_must_not_be_created(**_kwargs):
        pytest.fail("start() should not create a worker in an unsupported runtime")

    monkeypatch.setattr(connection_manager_module.threading, "Thread", thread_must_not_be_created)
    manager, _ = manager_factory(capabilities=capabilities)

    manager.start()

    assert expected_message in caplog.text


def test_stop_is_a_noop_for_an_already_disconnected_manager(manager_factory, caplog):
    manager, client = manager_factory()

    manager.stop()

    assert client.shutdown_calls == 0
    assert manager.get_state() == ConnectionState.DISCONNECTED.value
    assert "Stop called but already disconnected" in caplog.text


def test_stop_signals_worker_shuts_down_client_and_clears_runtime_data(ready_manager):
    manager, client = ready_manager(
        client=FakeMT5Client(
            terminal_info_result={"name": "MetaTrader 5"}, version_result="5.0.0"
        )
    )
    worker = ExistingWorker()
    manager._worker_thread = worker

    manager.stop()

    assert client.shutdown_calls == 1
    assert worker.join_timeouts == [2.0]
    assert manager._stop_event.is_set() is True
    assert manager.get_state() == ConnectionState.DISCONNECTED.value
    assert manager._mt5_initialized is False
    assert manager.get_terminal_info() is None
    assert manager.get_version() is None
    assert manager.get_health()["startupTime"] is None


def test_stop_records_shutdown_failure_but_completes_disconnection(ready_manager):
    manager, client = ready_manager(client=FakeMT5Client(shutdown_result=False))

    manager.stop()

    assert client.shutdown_calls == 1
    assert manager.get_last_error()["code"] == "MT5_SHUTDOWN_FAILED"
    assert manager.get_state() == ConnectionState.DISCONNECTED.value


def test_stop_records_shutdown_exceptions_but_never_raises(ready_manager, caplog):
    manager, client = ready_manager(
        client=FakeMT5Client(shutdown_result=RuntimeError("terminal did not respond"))
    )

    manager.stop()

    assert client.shutdown_calls == 1
    assert manager.get_last_error()["code"] == "MT5_SHUTDOWN_FAILED"
    assert "MT5_SHUTDOWN_EXCEPTION" in caplog.text
    assert manager.get_state() == ConnectionState.DISCONNECTED.value


def test_stop_warns_when_a_worker_does_not_exit_by_the_join_timeout(
    ready_manager, caplog
):
    manager, _ = ready_manager()
    worker = ExistingWorker(finish_on_join=False)
    manager._worker_thread = worker

    manager.stop()

    assert worker.join_timeouts == [2.0]
    assert "Worker thread did not exit within timeout" in caplog.text


def test_restart_stops_then_starts_the_same_manager(manager_factory, monkeypatch, caplog):
    RecordingThread.instances.clear()
    monkeypatch.setattr(connection_manager_module.threading, "Thread", RecordingThread)
    sleep = Mock()
    monkeypatch.setattr(connection_manager_module.time, "sleep", sleep)
    client = FakeMT5Client()
    manager, _ = manager_factory(client=client)
    assert manager._attempt_initialize_and_connect() is True

    manager.restart()

    assert client.shutdown_calls == 1
    assert sleep.call_args_list == [call(0.1)]
    assert len(RecordingThread.instances) == 1
    assert RecordingThread.instances[0].started is True
    assert "Reconnect requested" in caplog.text


def test_worker_connects_resets_retry_metadata_and_records_reconnect_time(
    manager_factory, monkeypatch, caplog
):
    manager, client = manager_factory(client=FakeMT5Client())
    manager._reconnect_count = 8
    manager._stop_event = ScriptedStopEvent([False, True])
    monkeypatch.setattr(connection_manager_module.time, "time", lambda: 1_700_000_000.0)

    manager._run()

    assert client.initialize_calls == [DEFAULT_SETTINGS["MT5_TERMINAL_PATH"]]
    assert manager.get_state() == ConnectionState.CONNECTED.value
    assert manager._reconnect_count == 0
    assert manager._last_reconnect_time == 1_700_000_000.0
    assert manager._startup_time == 1_700_000_000.0
    assert "Connection manager worker started" in caplog.text
    assert "Connection manager worker exiting" in caplog.text


def test_worker_applies_exponential_backoff_and_jitter_after_failure(
    manager_factory, monkeypatch, caplog
):
    client = FakeMT5Client(initialize_result=False)
    manager, _ = manager_factory(client=client)
    manager._stop_event = ScriptedStopEvent([False, True])
    jitter = Mock(return_value=0.25)
    monkeypatch.setattr(connection_manager_module.random, "uniform", jitter)
    sleep = Mock()
    monkeypatch.setattr(connection_manager_module.time, "sleep", sleep)

    manager._run()

    assert manager._reconnect_count == 1
    assert jitter.call_args_list == [call(0, 1.0)]
    assert sleep.call_args_list == []
    assert "Reconnect attempt 1 failed; sleeping for 2.25s before retry" in caplog.text


def test_worker_caps_exponential_backoff_on_subsequent_failures(
    manager_factory, monkeypatch
):
    client = FakeMT5Client(initialize_result=False)
    manager, _ = manager_factory(
        client=client,
        settings_values={
            **DEFAULT_SETTINGS,
            "MT5_RETRY_BASE_DELAY": 1.0,
            "MT5_RETRY_MAX_DELAY": 1.5,
            "MT5_MAX_RETRIES": 0,
        },
    )
    manager._stop_event = ScriptedStopEvent([False, False, False, False, True])
    jitter = Mock(return_value=0.0)
    monkeypatch.setattr(connection_manager_module.random, "uniform", jitter)
    sleep = Mock()
    monkeypatch.setattr(connection_manager_module.time, "sleep", sleep)

    manager._run()

    assert client.initialize_calls == [
        DEFAULT_SETTINGS["MT5_TERMINAL_PATH"],
        DEFAULT_SETTINGS["MT5_TERMINAL_PATH"],
    ]
    assert manager._reconnect_count == 2
    assert jitter.call_args_list == [call(0, 0.5), call(0, 0.75)]
    assert sleep.call_args_list == [call(0.5), call(0.5)]


def test_worker_enters_failed_state_at_the_configured_retry_limit(
    manager_factory, monkeypatch, caplog
):
    client = FakeMT5Client(initialize_result=False)
    manager, _ = manager_factory(
        client=client,
        settings_values={**DEFAULT_SETTINGS, "MT5_MAX_RETRIES": 1},
    )
    manager._stop_event = ScriptedStopEvent([False, True])
    monkeypatch.setattr(connection_manager_module.random, "uniform", lambda *_args: 0.0)
    monkeypatch.setattr(connection_manager_module.time, "sleep", Mock())

    manager._run()

    assert manager._reconnect_count == 1
    assert manager.get_state() == ConnectionState.FAILED.value
    assert "Max reconnect attempts (1) reached" in caplog.text


def test_worker_never_attempts_mt5_on_an_unsupported_platform(manager_factory, monkeypatch):
    manager, client = manager_factory(
        capabilities={"mt5Supported": False, "mt5Available": False}
    )
    manager._stop_event = ScriptedStopEvent([False, True])
    sleep = Mock()
    monkeypatch.setattr(connection_manager_module.time, "sleep", sleep)

    manager._run()

    assert client.initialize_calls == []
    assert sleep.call_args_list == [call(1.0)]


def test_worker_monitors_an_existing_connection_without_reinitializing(
    ready_manager, monkeypatch
):
    manager, client = ready_manager()
    manager._stop_event = ScriptedStopEvent([False, True])
    sleep = Mock()
    monkeypatch.setattr(connection_manager_module.time, "sleep", sleep)

    manager._run()

    assert len(client.initialize_calls) == 1
    assert sleep.call_args_list == [call(1.0)]


def test_worker_records_unexpected_dependency_exceptions_and_exits_cleanly(
    manager_factory, monkeypatch
):
    manager, _ = manager_factory(client=FakeMT5Client(initialize_result=False))
    manager._stop_event = ScriptedStopEvent([False, True])
    monkeypatch.setattr(
        connection_manager_module.random,
        "uniform",
        Mock(side_effect=RuntimeError("random source unavailable")),
    )
    sleep = Mock()
    monkeypatch.setattr(connection_manager_module.time, "sleep", sleep)

    manager._run()

    assert manager.get_last_error()["code"] == "WORKER_LOOP_EXCEPTION"
    assert "random source unavailable" in manager.get_last_error()["message"]
    assert sleep.call_args_list == [call(1.0)]


def test_health_and_capabilities_include_runtime_metadata(manager_factory, monkeypatch):
    manager, _ = manager_factory()
    manager._state = ConnectionState.CONNECTED
    manager._mt5_initialized = True
    manager._version = "5.0.4200"
    manager._startup_time = 100.0
    manager._last_reconnect_time = 120.0
    manager._reconnect_count = 2
    manager._last_error = {"code": "TEST", "message": "diagnostic", "timestamp": 90.0}
    monkeypatch.setattr(connection_manager_module.time, "time", lambda: 160.0)

    capabilities = manager.get_capabilities()
    health = manager.get_health()

    assert capabilities["state"] == "CONNECTED"
    assert capabilities["mt5Initialized"] is True
    assert capabilities["terminalVersion"] == "5.0.4200"
    assert capabilities["lastError"] == health["lastError"]
    assert health == {
        "connectionState": "CONNECTED",
        "mt5Initialized": True,
        "terminalVersion": "5.0.4200",
        "lastError": {"code": "TEST", "message": "diagnostic", "timestamp": 90.0},
        "startupTime": "1970-01-01T00:01:40+00:00",
        "uptimeSeconds": 60.0,
        "reconnectCount": 2,
        "lastReconnect": "1970-01-01T00:02:00+00:00",
    }


def test_disconnected_reads_return_safe_defaults_and_record_a_bridge_error(
    manager_factory
):
    manager, client = manager_factory()
    from_dt = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    to_dt = datetime.datetime(2025, 1, 2, tzinfo=datetime.timezone.utc)

    assert manager.fetch_account() is None
    assert manager.fetch_positions() == []
    assert manager.fetch_symbols() == []
    assert manager.fetch_symbol_info("EURUSD") is None
    assert manager.fetch_symbol_tick("EURUSD") is None
    assert manager.fetch_history_deals(from_dt, to_dt) == []
    assert manager.fetch_history_orders(from_dt, to_dt) == []
    assert manager.get_last_error()["code"] == "BRIDGE_NOT_CONNECTED"
    assert client.account_calls == 0
    assert client.positions_calls == 0
    assert client.symbols_calls == 0


def test_fetch_account_delegates_to_mt5_when_ready(ready_manager):
    manager, client = ready_manager()
    client.account_result = {"login": 123456, "balance": 1_000.0}

    assert manager.fetch_account() == {"login": 123456, "balance": 1_000.0}
    assert client.account_calls == 1


def test_fetch_positions_delegates_to_mt5_when_ready(ready_manager):
    manager, client = ready_manager()
    client.positions_result = [{"ticket": 1}, {"ticket": 2}]

    assert manager.fetch_positions() == [{"ticket": 1}, {"ticket": 2}]
    assert client.positions_calls == 1


def test_fetch_symbols_delegates_to_mt5_when_ready(ready_manager):
    manager, client = ready_manager()
    client.symbols_result = [{"name": "EURUSD"}, {"name": "GBPUSD"}]

    assert manager.fetch_symbols() == [{"name": "EURUSD"}, {"name": "GBPUSD"}]
    assert client.symbols_calls == 1


def test_fetch_symbol_info_and_tick_preserve_the_requested_symbol(ready_manager):
    manager, client = ready_manager()
    client.symbol_info_result = {"name": "XAUUSD", "digits": 2}
    client.symbol_tick_result = {"bid": 2400.0, "ask": 2400.2}

    assert manager.fetch_symbol_info("XAUUSD") == {"name": "XAUUSD", "digits": 2}
    assert manager.fetch_symbol_tick("XAUUSD") == {"bid": 2400.0, "ask": 2400.2}
    assert client.symbol_info_calls == ["XAUUSD"]
    assert client.symbol_tick_calls == ["XAUUSD"]


def test_fetch_history_proxies_preserve_dates_ticket_and_symbol(ready_manager):
    manager, client = ready_manager()
    from_dt = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    to_dt = datetime.datetime(2025, 1, 2, tzinfo=datetime.timezone.utc)

    assert manager.fetch_history_deals(from_dt, to_dt, ticket=101, symbol="EURUSD") == [
        {"ticket": 100}
    ]
    assert manager.fetch_history_orders(from_dt, to_dt, ticket=102, symbol="GBPUSD") == [
        {"ticket": 200}
    ]
    assert client.history_deals_calls == [(from_dt, to_dt, 101, "EURUSD")]
    assert client.history_orders_calls == [(from_dt, to_dt, 102, "GBPUSD")]


@pytest.mark.parametrize(
    ("client_attribute", "call_proxy", "expected", "error_code"),
    [
        (
            "account_result",
            lambda manager, start, end: manager.fetch_account(),
            None,
            "FETCH_ACCOUNT_FAILED",
        ),
        (
            "positions_result",
            lambda manager, start, end: manager.fetch_positions(),
            [],
            "FETCH_POSITIONS_FAILED",
        ),
        (
            "symbols_result",
            lambda manager, start, end: manager.fetch_symbols(),
            [],
            "FETCH_SYMBOLS_FAILED",
        ),
        (
            "symbol_info_result",
            lambda manager, start, end: manager.fetch_symbol_info("EURUSD"),
            None,
            "FETCH_SYMBOL_INFO_FAILED",
        ),
        (
            "symbol_tick_result",
            lambda manager, start, end: manager.fetch_symbol_tick("EURUSD"),
            None,
            "FETCH_SYMBOL_TICK_FAILED",
        ),
        (
            "history_deals_result",
            lambda manager, start, end: manager.fetch_history_deals(start, end),
            [],
            "FETCH_HISTORY_DEALS_FAILED",
        ),
        (
            "history_orders_result",
            lambda manager, start, end: manager.fetch_history_orders(start, end),
            [],
            "FETCH_HISTORY_ORDERS_FAILED",
        ),
    ],
)
def test_read_proxies_contain_mt5_exceptions_and_record_specific_error_codes(
    ready_manager, client_attribute, call_proxy, expected, error_code
):
    manager, client = ready_manager()
    setattr(client, client_attribute, RuntimeError("MT5 call failed"))
    start = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    end = datetime.datetime(2025, 1, 2, tzinfo=datetime.timezone.utc)

    assert call_proxy(manager, start, end) == expected
    assert manager.get_last_error()["code"] == error_code
    assert manager.get_last_error()["message"] == "MT5 call failed"


def test_concurrent_start_calls_create_only_one_worker(manager_factory, monkeypatch):
    RecordingThread.instances.clear()
    real_thread = threading.Thread
    monkeypatch.setattr(connection_manager_module.threading, "Thread", RecordingThread)
    manager, _ = manager_factory()
    barrier = threading.Barrier(12)
    failures = []

    def invoke_start():
        try:
            barrier.wait()
            manager.start()
        except BaseException as exc:  # pragma: no cover - assertion below reports it
            failures.append(exc)

    callers = [real_thread(target=invoke_start) for _ in range(12)]
    for caller in callers:
        caller.start()
    for caller in callers:
        caller.join(timeout=2.0)

    assert not failures
    assert all(not caller.is_alive() for caller in callers)
    assert len(RecordingThread.instances) == 1


def test_concurrent_reads_and_diagnostics_remain_safe_when_connected(ready_manager):
    manager, client = ready_manager()
    barrier = threading.Barrier(10)
    failures = []

    def read_and_inspect():
        try:
            barrier.wait()
            for _ in range(25):
                assert manager.fetch_account() == {"login": 123456}
                assert manager.fetch_positions() == [{"ticket": 10}]
                assert manager.fetch_symbols() == [{"name": "EURUSD"}]
                assert manager.get_capabilities()["state"] == "CONNECTED"
                assert manager.get_health()["connectionState"] == "CONNECTED"
        except BaseException as exc:  # pragma: no cover - assertion below reports it
            failures.append(exc)

    readers = [threading.Thread(target=read_and_inspect) for _ in range(10)]
    for reader in readers:
        reader.start()
    for reader in readers:
        reader.join(timeout=2.0)

    assert not failures
    assert all(not reader.is_alive() for reader in readers)
    assert client.account_calls == 250
    assert client.positions_calls == 250
    assert client.symbols_calls == 250
# ============================================================================
# ENTERPRISE EDGE-CASE TESTS
# Batch 1 of 2
# ============================================================================


def test_stop_during_reconnect_backoff_aborts_cleanly(manager_factory, monkeypatch):
    """
    If stop() is requested while the worker is waiting for a reconnect,
    the worker must terminate without attempting another initialize().
    """
    client = FakeMT5Client(initialize_result=False)

    manager, _ = manager_factory(client=client)

    manager._stop_event = ScriptedStopEvent([False, True])

    sleep = Mock()

    monkeypatch.setattr(connection_manager_module.time, "sleep", sleep)
    monkeypatch.setattr(connection_manager_module.random, "uniform", lambda *_: 0)

    manager._run()

    assert client.initialize_calls == [
        DEFAULT_SETTINGS["MT5_TERMINAL_PATH"]
    ]

    assert manager.get_state() in (
        ConnectionState.DISCONNECTED.value,
        ConnectionState.FAILED.value,
    )


def test_stop_is_idempotent_after_multiple_calls(ready_manager):
    """
    Enterprise requirement:
    stop() may be called repeatedly by service shutdown handlers.
    """

    manager, client = ready_manager()

    manager.stop()

    shutdowns = client.shutdown_calls

    manager.stop()
    manager.stop()
    manager.stop()

    assert client.shutdown_calls >= shutdowns

    assert manager.get_state() == ConnectionState.DISCONNECTED.value

    assert manager.is_connected() is False


def test_multiple_restart_requests_are_safe(manager_factory, monkeypatch):
    """
    restart() should never create multiple worker threads.
    """

    RecordingThread.instances.clear()

    monkeypatch.setattr(
        connection_manager_module.threading,
        "Thread",
        RecordingThread,
    )

    monkeypatch.setattr(
        connection_manager_module.time,
        "sleep",
        Mock(),
    )

    client = FakeMT5Client()

    manager, _ = manager_factory(client=client)

    assert manager._attempt_initialize_and_connect()

    manager.restart()
    manager.restart()
    manager.restart()

    assert len(RecordingThread.instances) == 1


def test_start_stop_start_stop_lifecycle(manager_factory, monkeypatch):
    """
    A ConnectionManager should survive repeated service lifecycle events.
    """

    RecordingThread.instances.clear()

    monkeypatch.setattr(
        connection_manager_module.threading,
        "Thread",
        RecordingThread,
    )

    client = FakeMT5Client()

    manager, _ = manager_factory(client=client)

    manager.start()

    assert len(RecordingThread.instances) == 1

    manager.stop()

    assert manager.get_state() == ConnectionState.DISCONNECTED.value

    manager.start()

    assert len(RecordingThread.instances) == 2

    manager.stop()

    assert manager.get_state() == ConnectionState.DISCONNECTED.value


def test_connected_reads_remain_safe_when_mt5_returns_none(ready_manager):
    """
    Some MT5 terminals occasionally return None instead of raising.
    The bridge must simply pass the values through safely.
    """

    manager, client = ready_manager()

    client.account_result = None
    client.positions_result = None
    client.symbols_result = None
    client.symbol_info_result = None
    client.symbol_tick_result = None
    client.history_deals_result = None
    client.history_orders_result = None

    assert manager.fetch_account() is None

    assert manager.fetch_positions() == []

    assert manager.fetch_symbols() == []

    assert manager.fetch_symbol_info("EURUSD") is None

    assert manager.fetch_symbol_tick("EURUSD") is None

    from_dt = datetime.datetime.utcnow()
    to_dt = from_dt

    assert manager.fetch_history_deals(from_dt, to_dt) == []

    assert manager.fetch_history_orders(from_dt, to_dt) == []
