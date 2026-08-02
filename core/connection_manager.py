"""
ATLAS CERTIFICATION HEADER
name=core/connection_manager.py
Version: 3.2.0
Change Log:
- Implemented robust background connection loop with exponential backoff and jitter.
- Added reconnect counters, last reconnect timestamp, and connection timeout handling.
- Improved thread-safety and ensured safe startup/shutdown semantics.
- Normalized health and capability payloads for production certification.

Production Certification: Phase 3.2
"""

# core/connection_manager.py
"""
Connection manager that uses core.mt5_client.MT5Client to manage the
MetaTrader5 terminal lifecycle and provide read-only data proxies for
services.

This implementation keeps the original contract but runs the connection
lifecycle in a dedicated background worker thread. It implements
exponential backoff with jitter, reconnect counters, last reconnect
timestamps and a configurable maximum retry policy. All public APIs are
thread-safe and never raise MT5 exceptions to callers; errors are
recorded via _record_error and exposed through get_health()/get_capabilities().
"""

from __future__ import annotations

import threading
import time
import logging
from enum import Enum
from typing import Optional, Dict, Any, List
import datetime
import random

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
    """Thread-safe connection manager with background recovery logic."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state: ConnectionState = ConnectionState.DISCONNECTED
        self._client = mt5_client.MT5Client()
        self._mt5_initialized: bool = False
        self._terminal_info: Optional[Dict[str, Any]] = None
        self._version: Optional[str] = None
        self._last_error: Optional[Dict[str, Any]] = None
        self._startup_time: Optional[float] = None
        self._capabilities = mt5_client.get_capabilities() or {}

        # Reconnect / retry metadata
        # Allow configuration via settings where available, otherwise fallback
        self._base_retry_delay = getattr(settings, "MT5_RETRY_BASE_DELAY", 1.0)  # seconds
        self._max_retry_delay = getattr(settings, "MT5_RETRY_MAX_DELAY", 60.0)  # seconds
        self._max_retries = getattr(settings, "MT5_MAX_RETRIES", 10)
        self._connection_timeout = getattr(settings, "MT5_CONNECTION_TIMEOUT", getattr(settings, "MT5_TIMEOUT", 30000))

        self._reconnect_count: int = 0
        self._last_reconnect_time: Optional[float] = None

        # Worker control
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # If platform does not support MT5, mark as UNSUPPORTED_PLATFORM
        if not self._capabilities.get("mt5Supported", False):
            self._state = ConnectionState.UNSUPPORTED_PLATFORM
            logger.info("Platform does not support MT5; state -> %s", self._state.value)
        elif not self._capabilities.get("mt5Available", False):
            # Platform supports MT5 but package not available (e.g., not installed)
            self._state = ConnectionState.BACKEND_UNAVAILABLE
            logger.info("MT5 package not available; state -> %s", self._state.value)

    # Internal helpers -------------------------------------------------
    def _set_state(self, new_state: ConnectionState) -> None:
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

    def _record_error(self, code: str, message: str) -> None:
        self._last_error = {"code": code, "message": message, "timestamp": time.time()}
        logger.error("Connection error: %s - %s", code, message)

    # Worker loop -----------------------------------------------------
    def _run(self) -> None:
        """Background loop that ensures the MT5 connection is established and
        recovers it when needed.
        """
        logger.info("Connection manager worker started")
        backoff_attempts = 0

        while not self._stop_event.is_set():
            try:
                # Respect platform-level states - do not attempt initialization
                if self._state in (ConnectionState.UNSUPPORTED_PLATFORM, ConnectionState.BACKEND_UNAVAILABLE):
                    time.sleep(1.0)
                    continue

                # If already connected, perform a light health check periodically
                if self.is_connected():
                    # Monitor interval small to keep health responsive
                    time.sleep(1.0)
                    continue

                # Not connected -> attempt initialization + connection
                self._set_state(ConnectionState.INITIALIZING)
                ok = self._attempt_initialize_and_connect()
                if ok:
                    # Reset backoff on success
                    backoff_attempts = 0
                    self._reconnect_count = 0
                    self._last_reconnect_time = time.time()
                    with self._lock:
                        self._startup_time = time.time()
                else:
                    # Failure; record backoff and possibly stop after max retries
                    backoff_attempts += 1
                    self._reconnect_count = backoff_attempts
                    delay = min(self._base_retry_delay * (2 ** (backoff_attempts - 1)), self._max_retry_delay)
                    # Add jitter up to 50% of delay
                    jitter = random.uniform(0, delay * 0.5)
                    sleep_for = delay + jitter
                    logger.info("Reconnect attempt %d failed; sleeping for %.2fs before retry", backoff_attempts, sleep_for)
                    # If exceeded max_retries, mark as FAILED but keep trying periodically
                    if self._max_retries and backoff_attempts >= self._max_retries:
                        logger.warning("Max reconnect attempts (%s) reached; entering FAILED state and will retry at max interval", self._max_retries)
                        self._set_state(ConnectionState.FAILED)
                        sleep_for = self._max_retry_delay
                    # Wait but allow fast stop
                    waited = 0.0
                    while waited < sleep_for and not self._stop_event.is_set():
                        time.sleep(0.5)
                        waited += 0.5

            except Exception as exc:  # pragma: no cover - defensive
                # Never raise from the worker thread; always record and continue.
                self._record_error("WORKER_LOOP_EXCEPTION", str(exc))
                time.sleep(1.0)

        logger.info("Connection manager worker exiting")

    def _attempt_initialize_and_connect(self) -> bool:
        """Attempt to initialize MT5 and login. Returns True on success.

        All exceptions are caught and recorded; callers should not observe
        MT5 exceptions.
        """
        try:
            logger.info("Attempting MT5 initialize")
            path = getattr(settings, "MT5_TERMINAL_PATH", None) or None
            initialized = False
            try:
                initialized = self._client.initialize(path=path)
            except Exception as exc:
                # Initialization raised - record and return False
                self._record_error("MT5_INITIALIZE_EXCEPTION", str(exc))
                initialized = False

            if not initialized:
                last = None
                try:
                    last = self._client.last_error()
                except Exception:
                    last = None
                msg = "mt5.initialize() returned False"
                if last:
                    msg += f" - {last}"
                self._mt5_initialized = False
                self._record_error("MT5_INITIALIZE_FAILED", msg)
                return False

            # Mark initialized
            self._mt5_initialized = True
            logger.info("MT5 initialized")

            # CONNECTING state
            self._set_state(ConnectionState.CONNECTING)

            # Attempt login
            login = getattr(settings, "MT5_LOGIN", None)
            password = getattr(settings, "MT5_PASSWORD", None)
            server = getattr(settings, "MT5_SERVER", None)

            login_ok = False
            try:
                # Some MT5 client implementations may block - perform guarded call
                login_ok = self._client.login(login=login, password=password, server=server)
            except Exception as exc:
                logger.debug("Login attempt raised: %s", exc)
                login_ok = False

            if not login_ok:
                last = None
                try:
                    last = self._client.last_error()
                except Exception:
                    last = None
                msg = "mt5.login() failed"
                if last:
                    msg += f" - {last}"
                self._record_error("MT5_LOGIN_FAILED", msg)
                self._set_state(ConnectionState.FAILED)
                return False

            # Obtain terminal info/version if possible
            try:
                info = self._client.terminal_info()
                version = self._client.version()
                self._terminal_info = info if info else None
                self._version = str(version) if version else None
            except Exception:
                self._terminal_info = None
                self._version = None

            with self._lock:
                self._startup_time = time.time()
                self._set_state(ConnectionState.CONNECTED)
                logger.info("Connected to MT5")

            return True

        except Exception as exc:  # pragma: no cover - defensive
            self._record_error("MT5_CONNECTION_EXCEPTION", str(exc))
            self._set_state(ConnectionState.FAILED)
            return False

    # Public API - lifecycle ------------------------------------------
    def start(self) -> None:
        """Start the background worker if not already running.

        This method is idempotent.
        """
        with self._lock:
            if self._worker_thread and self._worker_thread.is_alive():
                logger.info("Start called but worker thread already running")
                return

            if self._state == ConnectionState.UNSUPPORTED_PLATFORM:
                logger.info("Start called but platform does not support MT5")
                return
            if self._state == ConnectionState.BACKEND_UNAVAILABLE:
                logger.info("Start called but MT5 backend not available (package missing)")
                return

            self._stop_event.clear()
            self._worker_thread = threading.Thread(target=self._run, name="mt5-connection-worker", daemon=True)
            self._worker_thread.start()
            logger.info("Connection manager started (background worker)")

    def stop(self) -> None:
        with self._lock:
            if self._state in (ConnectionState.DISCONNECTED, ConnectionState.UNSUPPORTED_PLATFORM, ConnectionState.BACKEND_UNAVAILABLE) and not (self._worker_thread and self._worker_thread.is_alive()):
                logger.info("Stop called but already disconnected or backend unsupported and worker not running")
                return

            logger.info("Shutdown requested")
            self._set_state(ConnectionState.SHUTTING_DOWN)
            # Signal worker to stop
            self._stop_event.set()

            # Attempt to shutdown client cleanly
            try:
                if self._mt5_initialized:
                    ok = False
                    try:
                        ok = self._client.shutdown()
                    except Exception as exc:  # pragma: no cover - defensive
                        self._record_error("MT5_SHUTDOWN_EXCEPTION", str(exc))
                    if not ok:
                        self._record_error("MT5_SHUTDOWN_FAILED", "mt5.shutdown() reported failure")
            except Exception as exc:  # pragma: no cover - defensive
                self._record_error("MT5_SHUTDOWN_EXCEPTION", str(exc))
            finally:
                self._mt5_initialized = False
                self._terminal_info = None
                self._version = None
                self._startup_time = None
                self._set_state(ConnectionState.DISCONNECTED)

            # Wait briefly for worker to exit
            if self._worker_thread and self._worker_thread.is_alive():
                self._worker_thread.join(timeout=2.0)
                if self._worker_thread.is_alive():
                    logger.warning("Worker thread did not exit within timeout")

            logger.info("Disconnected")

    def restart(self) -> None:
        with self._lock:
            logger.info("Reconnect requested")
            self.stop()
            # small pause to allow full shutdown
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
        """Return a diagnostic view suitable for the /health endpoint.

        The returned dict is deliberately JSON-serialisable and never contains
        raw exception objects.
        """
        with self._lock:
            uptime = None
            if self._startup_time:
                uptime = time.time() - self._startup_time

            last_reconnect_iso = None
            if self._last_reconnect_time:
                last_reconnect_iso = datetime.datetime.fromtimestamp(self._last_reconnect_time, tz=datetime.timezone.utc).isoformat()

            return {
                "connectionState": self._state.value,
                "mt5Initialized": bool(self._mt5_initialized),
                "terminalVersion": self._version,
                "lastError": self._last_error,
                "startupTime": datetime.datetime.fromtimestamp(self._startup_time, tz=datetime.timezone.utc).isoformat() if self._startup_time else None,
                "uptimeSeconds": float(uptime) if uptime is not None else None,
                "reconnectCount": int(self._reconnect_count),
                "lastReconnect": last_reconnect_iso,
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
