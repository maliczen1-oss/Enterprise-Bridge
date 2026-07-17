# core/connection_manager.py
"""
Connection manager that uses core.mt5_client.MT5Client to manage the
MetaTrader5 terminal lifecycle.

Public interface:
    start()
    stop()
    restart()
    is_connected()
    get_state()
    get_terminal_info()
    get_version()
    get_last_error()
    get_health()
"""
import threading
import time
import logging
from enum import Enum
from typing import Optional, Dict, Any

from config import settings
from core.mt5_client import MT5Client, MT5UnavailableError

logger = logging.getLogger("bridge")

class ConnectionState(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    INITIALIZING = "INITIALIZING"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    FAILED = "FAILED"
    SHUTTING_DOWN = "SHUTTING_DOWN"

class ConnectionManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._state: ConnectionState = ConnectionState.DISCONNECTED
        self._client = MT5Client()
        self._mt5_initialized: bool = False
        self._terminal_info: Optional[Dict[str, Any]] = None
        self._version: Optional[str] = None
        self._last_error: Optional[Dict[str, Any]] = None
        self._startup_time: Optional[float] = None

    # Internal helpers
    def _set_state(self, new_state: ConnectionState):
        with self._lock:
            prev = self._state
            if not self._is_legal_transition(prev, new_state):
                logger.warning("Illegal state transition attempted from %s to %s", prev.value, new_state.value)
                return
            self._state = new_state
            logger.info("Connection state -> %s", new_state.value)

    def _is_legal_transition(self, prev: ConnectionState, new: ConnectionState) -> bool:
        allowed = {
            ConnectionState.DISCONNECTED: {ConnectionState.INITIALIZING, ConnectionState.SHUTTING_DOWN},
            ConnectionState.INITIALIZING: {ConnectionState.CONNECTING, ConnectionState.FAILED, ConnectionState.SHUTTING_DOWN},
            ConnectionState.CONNECTING: {ConnectionState.CONNECTED, ConnectionState.FAILED, ConnectionState.SHUTTING_DOWN},
            ConnectionState.CONNECTED: {ConnectionState.SHUTTING_DOWN, ConnectionState.DISCONNECTED, ConnectionState.FAILED},
            ConnectionState.FAILED: {ConnectionState.INITIALIZING, ConnectionState.SHUTTING_DOWN, ConnectionState.DISCONNECTED},
            ConnectionState.SHUTTING_DOWN: {ConnectionState.DISCONNECTED},
        }
        return new in allowed.get(prev, set())

    def _record_error(self, code: str, message: str):
        self._last_error = {"code": code, "message": message, "timestamp": time.time()}
        logger.error("Connection error: %s - %s", code, message)

    # Public API
    def start(self):
        with self._lock:
            if self._state in (ConnectionState.CONNECTED, ConnectionState.CONNECTING, ConnectionState.INITIALIZING):
                logger.info("Start called but connection manager already in state %s", self._state.value)
                return

            logger.info("Bridge Starting")
            self._set_state(ConnectionState.INITIALIZING)

            # Initialize MT5 client
            logger.info("Initializing MT5")
            try:
                try:
                    path = settings.MT5_TERMINAL_PATH or None
                    initialized = self._client.initialize(path=path)
                except MT5UnavailableError as exc:
                    self._mt5_initialized = False
                    self._record_error("MT5_IMPORT_FAILED", str(exc))
                    self._set_state(ConnectionState.FAILED)
                    return

                if not initialized:
                    last = self._client.last_error()
                    msg = "mt5.initialize() returned False"
                    if last:
                        msg += f" - {last}"
                    self._mt5_initialized = False
                    self._record_error("MT5_INITIALIZE_FAILED", msg)
                    self._set_state(ConnectionState.FAILED)
                    return

                self._mt5_initialized = True
                logger.info("MT5 initialized")

            except Exception as exc:
                self._mt5_initialized = False
                self._record_error("MT5_INITIALIZE_EXCEPTION", str(exc))
                self._set_state(ConnectionState.FAILED)
                return

            # Attempt login / connect
            self._set_state(ConnectionState.CONNECTING)
            logger.info("Connecting")
            try:
                login = settings.MT5_LOGIN
                password = settings.MT5_PASSWORD
                server = settings.MT5_SERVER

                # Do not log credentials
                login_ok = False
                try:
                    login_ok = self._client.login(login=login, password=password, server=server)
                except Exception as exc:
                    logger.debug("Login attempt raised: %s", exc)
                    login_ok = False

                if not login_ok:
                    last = self._client.last_error()
                    msg = "mt5.login() failed"
                    if last:
                        msg += f" - {last}"
                    self._record_error("MT5_LOGIN_FAILED", msg)
                    self._set_state(ConnectionState.FAILED)
                    return

                # Record terminal info and version
                try:
                    info = self._client.terminal_info()
                    version = self._client.version()
                    self._terminal_info = info if info else None
                    self._version = str(version) if version else None
                except Exception:
                    self._terminal_info = None
                    self._version = None

                self._startup_time = time.time()
                self._set_state(ConnectionState.CONNECTED)
                logger.info("Connected")

            except Exception as exc:
                self._record_error("MT5_CONNECTION_EXCEPTION", str(exc))
                self._set_state(ConnectionState.FAILED)
                return

    def stop(self):
        with self._lock:
            if self._state == ConnectionState.DISCONNECTED:
                logger.info("Stop called but already disconnected")
                return

            logger.info("Shutdown")
            self._set_state(ConnectionState.SHUTTING_DOWN)

            try:
                if self._mt5_initialized:
                    ok = self._client.shutdown()
                    if not ok:
                        self._record_error("MT5_SHUTDOWN_FAILED", "mt5.shutdown() reported failure")
                # Clear state regardless of shutdown success
            except Exception as exc:
                self._record_error("MT5_SHUTDOWN_EXCEPTION", str(exc))
            finally:
                self._mt5_initialized = False
                self._terminal_info = None
                self._version = None
                self._startup_time = None
                self._set_state(ConnectionState.DISCONNECTED)
                logger.info("Disconnected")

    def restart(self):
        with self._lock:
            logger.info("Reconnect Attempt")
            # stop then start
            self.stop()
            # small backoff
            time.sleep(0.1)
            self.start()

    def is_connected(self) -> bool:
        with self._lock:
            return self._state == ConnectionState.CONNECTED

    def get_state(self) -> str:
        with self._lock:
            return self._state.value

    def get_terminal_info(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._terminal_info

    def get_version(self) -> Optional[str]:
        with self._lock:
            return self._version

    def get_last_error(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._last_error

    def get_health(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "connectionState": self._state.value,
                "mt5Initialized": bool(self._mt5_initialized),
                "terminalVersion": self._version,
                "lastError": self._last_error,
                "startupTime": self._startup_time,
            }

# Module-level singleton for wiring in app
manager = ConnectionManager()
