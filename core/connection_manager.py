# core/connection_manager.py
"""
Connection manager that uses core.mt5_client.MT5Client to manage the
MetaTrader5 terminal lifecycle and provide read-only data proxies for
services.

This version treats MT5 as optional and exposes capability information.
When MT5 is not supported on the platform, the manager enters
UNSUPPORTED_PLATFORM state and will not attempt initialization.
"""
import threading
import time
import logging
from enum import Enum
from typing import Optional, Dict, Any, List
import datetime

from config import settings
from core import mt5_client

logger = logging.getLogger("bridge")


class ConnectionState(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    INITIALIZING = "INITIALIZING"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    FAILED = "FAILED"
    SHUTTING_DOWN = "SHUTTING_DOWN"
    UNSUPPORTED_PLATFORM = "UNSUPPORTED_PLATFORM"
    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"


class ConnectionManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._state: ConnectionState = ConnectionState.DISCONNECTED
        self._client = mt5_client.MT5Client()
        self._mt5_initialized: bool = False
        self._terminal_info: Optional[Dict[str, Any]] = None
        self._version: Optional[str] = None
        self._last_error: Optional[Dict[str, Any]] = None
        self._startup_time: Optional[float] = None
        self._capabilities = mt5_client.get_capabilities()

        # If platform does not support MT5, mark as UNSUPPORTED_PLATFORM
        if not self._capabilities.get("mt5Supported", False):
            self._state = ConnectionState.UNSUPPORTED_PLATFORM
            logger.info("Platform does not support MT5; state -> %s", self._state.value)
        elif not self._capabilities.get("mt5Available", False):
            # Platform supports MT5 but package not available (e.g., not installed)
            self._state = ConnectionState.BACKEND_UNAVAILABLE
            logger.info("MT5 package not available; state -> %s", self._state.value)

    # Internal helpers -------------------------------------------------
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
            ConnectionState.DISCONNECTED: {ConnectionState.INITIALIZING, ConnectionState.SHUTTING_DOWN, ConnectionState.UNSUPPORTED_PLATFORM, ConnectionState.BACKEND_UNAVAILABLE},
            ConnectionState.INITIALIZING: {ConnectionState.CONNECTING, ConnectionState.FAILED, ConnectionState.SHUTTING_DOWN},
            ConnectionState.CONNECTING: {ConnectionState.CONNECTED, ConnectionState.FAILED, ConnectionState.SHUTTING_DOWN},
            ConnectionState.CONNECTED: {ConnectionState.SHUTTING_DOWN, ConnectionState.DISCONNECTED, ConnectionState.FAILED},
            ConnectionState.FAILED: {ConnectionState.INITIALIZING, ConnectionState.SHUTTING_DOWN, ConnectionState.DISCONNECTED},
            ConnectionState.SHUTTING_DOWN: {ConnectionState.DISCONNECTED},
            ConnectionState.UNSUPPORTED_PLATFORM: {ConnectionState.DISCONNECTED},
            ConnectionState.BACKEND_UNAVAILABLE: {ConnectionState.INITIALIZING, ConnectionState.DISCONNECTED},
        }
        return new in allowed.get(prev, set())

    def _record_error(self, code: str, message: str):
        self._last_error = {"code": code, "message": message, "timestamp": time.time()}
        logger.error("Connection error: %s - %s", code, message)

    # Public API - lifecycle ------------------------------------------
    def start(self):
        with self._lock:
            # If platform unsupported or backend unavailable, do not attempt init
            if self._state == ConnectionState.UNSUPPORTED_PLATFORM:
                logger.info("Start called but platform does not support MT5")
                return
            if self._state == ConnectionState.BACKEND_UNAVAILABLE:
                logger.info("Start called but MT5 backend not available (package missing)")
                return

            if self._state in (ConnectionState.CONNECTED, ConnectionState.CONNECTING, ConnectionState.INITIALIZING):
                logger.info("Start called but connection manager already in state %s", self._state.value)
                return

            logger.info("Bridge Starting")
            self._set_state(ConnectionState.INITIALIZING)

            logger.info("Initializing MT5")
            try:
                path = settings.MT5_TERMINAL_PATH or None
                initialized = self._client.initialize(path=path)
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
            if self._state in (ConnectionState.DISCONNECTED, ConnectionState.UNSUPPORTED_PLATFORM, ConnectionState.BACKEND_UNAVAILABLE):
                logger.info("Stop called but already disconnected or backend unsupported")
                return

            logger.info("Shutdown")
            self._set_state(ConnectionState.SHUTTING_DOWN)

            try:
                if self._mt5_initialized:
                    ok = self._client.shutdown()
                    if not ok:
                        self._record_error("MT5_SHUTDOWN_FAILED", "mt5.shutdown() reported failure")
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
            self.stop()
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

    def get_capabilities(self) -> Dict[str, Any]:
        """
        Return the capability model from mt5_client plus runtime flags.
        """
        with self._lock:
            caps = dict(self._capabilities)
            caps.update({
                "state": self._state.value,
                "mt5Initialized": bool(self._mt5_initialized),
                "terminalVersion": self._version,
                "lastError": self._last_error,
            })
            return caps

    def get_health(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "connectionState": self._state.value,
                "mt5Initialized": bool(self._mt5_initialized),
                "terminalVersion": self._version,
                "lastError": self._last_error,
                "startupTime": self._startup_time,
            }

    # Read-only proxies for services -----------------------------------
    def _ensure_ready_for_reads(self) -> bool:
        with self._lock:
            if self._state != ConnectionState.CONNECTED or not self._mt5_initialized:
                self._record_error("BRIDGE_NOT_CONNECTED", "Bridge is not connected to MT5")
                return False
            return True

    def fetch_account(self) -> Optional[Dict[str, Any]]:
        if not self._ensure_ready_for_reads():
            return None
        try:
            return self._client.account_info()
        except Exception as exc:
            self._record_error("FETCH_ACCOUNT_FAILED", str(exc))
            return None

    def fetch_positions(self) -> List[Dict[str, Any]]:
        if not self._ensure_ready_for_reads():
            return []
        try:
            return self._client.positions_get()
        except Exception as exc:
            self._record_error("FETCH_POSITIONS_FAILED", str(exc))
            return []

    def fetch_symbols(self) -> List[Dict[str, Any]]:
        if not self._ensure_ready_for_reads():
            return []
        try:
            return self._client.symbols_get()
        except Exception as exc:
            self._record_error("FETCH_SYMBOLS_FAILED", str(exc))
            return []

    def fetch_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not self._ensure_ready_for_reads():
            return None
        try:
            return self._client.symbol_info(symbol)
        except Exception as exc:
            self._record_error("FETCH_SYMBOL_INFO_FAILED", str(exc))
            return None

    def fetch_symbol_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not self._ensure_ready_for_reads():
            return None
        try:
            return self._client.symbol_info_tick(symbol)
        except Exception as exc:
            self._record_error("FETCH_SYMBOL_TICK_FAILED", str(exc))
            return None

    def fetch_history_deals(self, from_dt: datetime.datetime, to_dt: datetime.datetime, ticket: Optional[int] = None, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self._ensure_ready_for_reads():
            return []
        try:
            return self._client.history_deals_get(from_dt, to_dt, ticket=ticket, symbol=symbol)
        except Exception as exc:
            self._record_error("FETCH_HISTORY_DEALS_FAILED", str(exc))
            return []

    def fetch_history_orders(self, from_dt: datetime.datetime, to_dt: datetime.datetime, ticket: Optional[int] = None, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self._ensure_ready_for_reads():
            return []
        try:
            return self._client.history_orders_get(from_dt, to_dt, ticket=ticket, symbol=symbol)
        except Exception as exc:
            self._record_error("FETCH_HISTORY_ORDERS_FAILED", str(exc))
            return []


# Module-level singleton for wiring in app
manager = ConnectionManager()
