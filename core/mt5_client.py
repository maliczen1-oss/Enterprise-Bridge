# core/mt5_client.py
"""
Thin wrapper around the MetaTrader5 Python bindings.

This module makes MetaTrader5 optional. Import errors do not prevent the
application from starting. The module exposes a capability model describing
the runtime environment and whether MT5 is available/supported.

All MT5-specific calls are centralized here. Callers should check
MT5_AVAILABLE and/or use ConnectionManager which wraps this client and
exposes higher-level runtime states.
"""
from typing import Any, Dict, List, Optional
import logging
import platform
import datetime

logger = logging.getLogger("bridge")

# Attempt to import MetaTrader5 but do not raise on ImportError.
try:
    import MetaTrader5 as mt5  # type: ignore
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore
    MT5_AVAILABLE = False

# Determine platform capability: MetaTrader5 official Python package is
# supported on Windows. On Linux/macOS the package may be unavailable.
PLATFORM = platform.system().lower()


def get_capabilities() -> Dict[str, Any]:
    """
    Return a capability model describing the runtime environment and MT5
    availability/support status.
    Example:
    {
      "platform": "linux",
      "mt5Supported": False,
      "mt5Available": False,
      "backend": "disabled"
    }
    """
    mt5_supported = PLATFORM == "windows"
    mt5_available = MT5_AVAILABLE and mt5 is not None and mt5_supported
    backend = "enabled" if mt5_available else "disabled"
    return {
        "platform": PLATFORM,
        "mt5Supported": mt5_supported,
        "mt5Available": mt5_available,
        "backend": backend,
    }


class MT5UnavailableError(RuntimeError):
    """Raised when MT5 is not available on this platform."""


class MT5Client:
    """
    Wrapper around MetaTrader5. Callers must check MT5_AVAILABLE or use
    get_capabilities() before invoking methods.
    """

    def __init__(self):
        self._mt5 = mt5 if MT5_AVAILABLE else None
        self._initialized = False

    # Lifecycle -----------------------------------------------------------
    def initialize(self, path: Optional[str] = None) -> bool:
        """
        Initialize the MT5 terminal. Returns True on success, False otherwise.
        If MT5 is not available on this platform, returns False.
        """
        if not MT5_AVAILABLE:
            logger.debug("MT5 initialize called but MT5 is not available on this platform.")
            return False
        try:
            if path:
                try:
                    result = self._mt5.initialize(path)
                except TypeError:
                    result = self._mt5.initialize(path=path)
            else:
                result = self._mt5.initialize()
            self._initialized = bool(result)
            return self._initialized
        except Exception as exc:
            logger.debug("mt5.initialize() raised: %s", exc)
            self._initialized = False
            return False

    def login(self, login: Optional[int] = None, password: Optional[str] = None, server: Optional[str] = None) -> bool:
        """
        Attempt to login. If MT5 is not available, return False.
        If login/password are None, assume the terminal is already connected.
        """
        if not MT5_AVAILABLE:
            logger.debug("MT5 login called but MT5 is not available on this platform.")
            return False

        if not self._initialized:
            try:
                self._mt5.initialize()
                self._initialized = True
            except Exception:
                pass

        if login is None and password is None:
            return True

        try:
            if login is not None and password is not None and server:
                result = self._mt5.login(login, password, server)
            elif login is not None and password is not None:
                result = self._mt5.login(login, password)
            else:
                return False

            if isinstance(result, bool):
                return result
            if isinstance(result, (tuple, list)):
                return bool(result[0]) if result else False
            if isinstance(result, dict):
                return bool(result.get("retcode", 0) == 0)
            return bool(result)
        except Exception as exc:
            logger.debug("mt5.login() raised: %s", exc)
            return False

    def shutdown(self) -> bool:
        """
        Shutdown the MT5 terminal connection. Returns True on success.
        If MT5 is not available, return True (nothing to do).
        """
        if not MT5_AVAILABLE or not self._mt5:
            return True
        try:
            result = self._mt5.shutdown()
            self._initialized = False
            return bool(result) if result is not None else True
        except Exception as exc:
            logger.debug("mt5.shutdown() raised: %s", exc)
            self._initialized = False
            return False

    # Introspection ------------------------------------------------------
    def terminal_info(self) -> Optional[Dict[str, Any]]:
        if not MT5_AVAILABLE or not self._mt5:
            return None
        try:
            info = self._mt5.terminal_info()
            return info._asdict() if hasattr(info, "_asdict") else (dict(info) if isinstance(info, dict) else None)
        except Exception as exc:
            logger.debug("mt5.terminal_info() raised: %s", exc)
            return None

    def version(self) -> Optional[str]:
        if not MT5_AVAILABLE or not self._mt5:
            return None
        try:
            ver = self._mt5.version()
            return str(ver) if ver is not None else None
        except Exception as exc:
            logger.debug("mt5.version() raised: %s", exc)
            return None

    def last_error(self) -> Optional[Dict[str, Any]]:
        if not MT5_AVAILABLE or not self._mt5:
            return None
        try:
            last = self._mt5.last_error()
            return last if last else None
        except Exception as exc:
            logger.debug("mt5.last_error() raised: %s", exc)
            return None

    # Read-only data access ---------------------------------------------
    def account_info(self) -> Optional[Dict[str, Any]]:
        if not MT5_AVAILABLE or not self._mt5:
            return None
        try:
            info = self._mt5.account_info()
            return info._asdict() if hasattr(info, "_asdict") else (dict(info) if isinstance(info, dict) else None)
        except Exception as exc:
            logger.debug("mt5.account_info() raised: %s", exc)
            return None

    def positions_get(self) -> List[Dict[str, Any]]:
        if not MT5_AVAILABLE or not self._mt5:
            return []
        try:
            positions = self._mt5.positions_get()
            if not positions:
                return []
            out = []
            for p in positions:
                out.append(p._asdict() if hasattr(p, "_asdict") else (dict(p) if isinstance(p, dict) else {}))
            return out
        except Exception as exc:
            logger.debug("mt5.positions_get() raised: %s", exc)
            return []

    def symbols_get(self) -> List[Dict[str, Any]]:
        if not MT5_AVAILABLE or not self._mt5:
            return []
        try:
            syms = self._mt5.symbols_get()
            if not syms:
                return []
            out = []
            for s in syms:
                out.append(s._asdict() if hasattr(s, "_asdict") else (dict(s) if isinstance(s, dict) else {}))
            return out
        except Exception as exc:
            logger.debug("mt5.symbols_get() raised: %s", exc)
            return []

    def symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not MT5_AVAILABLE or not self._mt5:
            return None
        try:
            info = self._mt5.symbol_info(symbol)
            return info._asdict() if hasattr(info, "_asdict") else (dict(info) if isinstance(info, dict) else None)
        except Exception as exc:
            logger.debug("mt5.symbol_info(%s) raised: %s", symbol, exc)
            return None

    def symbol_info_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not MT5_AVAILABLE or not self._mt5:
            return None
        try:
            tick = self._mt5.symbol_info_tick(symbol)
            return tick._asdict() if hasattr(tick, "_asdict") else (dict(tick) if isinstance(tick, dict) else None)
        except Exception as exc:
            logger.debug("mt5.symbol_info_tick(%s) raised: %s", symbol, exc)
            return None

    def history_deals_get(self, from_dt: datetime.datetime, to_dt: datetime.datetime, ticket: Optional[int] = None, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        if not MT5_AVAILABLE or not self._mt5:
            return []
        try:
            if ticket is not None:
                deals = self._mt5.history_deals_get(from_dt, to_dt, ticket)
            elif symbol:
                deals = self._mt5.history_deals_get(from_dt, to_dt, symbol)
            else:
                deals = self._mt5.history_deals_get(from_dt, to_dt)
            if not deals:
                return []
            out = []
            for d in deals:
                out.append(d._asdict() if hasattr(d, "_asdict") else (dict(d) if isinstance(d, dict) else {}))
            return out
        except Exception as exc:
            logger.debug("mt5.history_deals_get() raised: %s", exc)
            return []

    def history_orders_get(self, from_dt: datetime.datetime, to_dt: datetime.datetime, ticket: Optional[int] = None, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        if not MT5_AVAILABLE or not self._mt5:
            return []
        try:
            if ticket is not None:
                orders = self._mt5.history_orders_get(from_dt, to_dt, ticket)
            elif symbol:
                orders = self._mt5.history_orders_get(from_dt, to_dt, symbol)
            else:
                orders = self._mt5.history_orders_get(from_dt, to_dt)
            if not orders:
                return []
            out = []
            for o in orders:
                out.append(o._asdict() if hasattr(o, "_asdict") else (dict(o) if isinstance(o, dict) else {}))
            return out
        except Exception as exc:
            logger.debug("mt5.history_orders_get() raised: %s", exc)
            return []
