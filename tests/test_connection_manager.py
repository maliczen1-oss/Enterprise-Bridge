import pytest
import time
from services.connection_manager import ConnectionManager, ConnectionState

class DummyWorker:
    def __init__(self):
        self.started = False
        self.stopped = False
    def start(self):
        self.started = True
    def stop(self):
        self.stopped = True

@pytest.fixture
def manager():
    return ConnectionManager()

def test_initial_state(manager):
    assert manager.state == ConnectionState.DISCONNECTED

def test_startup_sets_connecting(manager):
    manager.startup()
    assert manager.state in (ConnectionState.CONNECTING, ConnectionState.CONNECTED)

def test_shutdown_sets_shutdown(manager):
    manager.startup()
    manager.shutdown()
    assert manager.state == ConnectionState.SHUTDOWN

def test_reconnect_transitions(manager):
    manager.startup()
    manager.state = ConnectionState.FAILED
    manager.reconnect()
    assert manager.state in (ConnectionState.RETRYING, ConnectionState.CONNECTED)

def test_retry_logic(manager):
    manager.state = ConnectionState.FAILED
    manager.retry()
    assert manager.state in (ConnectionState.RETRYING, ConnectionState.CONNECTED)

def test_failure_recovery(manager):
    manager.state = ConnectionState.FAILED
    manager.recover()
    assert manager.state in (ConnectionState.CONNECTING, ConnectionState.CONNECTED)

def test_health_state_transitions(manager):
    manager.state = ConnectionState.CONNECTED
    assert manager.is_healthy()
    manager.state = ConnectionState.FAILED
    assert not manager.is_healthy()

def test_exception_propagation(manager):
    def bad_startup():
        raise RuntimeError("Boom")
    manager._do_startup = bad_startup
    with pytest.raises(RuntimeError):
        manager.startup()

def test_worker_lifecycle(manager):
    worker = DummyWorker()
    manager.worker = worker
    manager.startup()
    assert worker.started
    manager.shutdown()
    assert worker.stopped

@pytest.mark.parametrize("state", [
    ConnectionState.CONNECTED,
    ConnectionState.CONNECTING,
    ConnectionState.DISCONNECTED,
    ConnectionState.FAILED,
    ConnectionState.UNSUPPORTED_PLATFORM,
    ConnectionState.BROKER_UNAVAILABLE,
    ConnectionState.RETRYING,
    ConnectionState.SHUTDOWN,
])
def test_all_states(manager, state):
    manager.state = state
    assert manager.state == state
