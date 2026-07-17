# core/mt5_client.py
"""
Thin wrapper around the MetaTrader5 Python bindings.

This module centralizes all direct imports and calls to the MetaTrader5
library so the rest of the codebase can be tested/mocked without importing
the real MT5 package.

All methods return Python-native structures (dicts, lists, primitives) or
None on failure. They never raise MetaTrader5-specific exceptions to callers;
errors are logged and None/empty lists are returned so the ConnectionManager
can translate them into bridge-level errors.
"""
from typing import Any, Optional, Dict, List
import logging
import datetime

logger = logging.getLogger("bridge")


class MT5UnavailableError(RuntimeError):
    """Raised when the MetaTrader5 package cannot be imported."""


class MT5Client:
    def __init__(self):
        self._mt5 = None
        self._initialized = False
        self._loaded = False

    def _ensure_imported(self) -> None:
        if self._loaded:
            return
        try:
            import MetaTrader5 as mt5  # type: ignore
        except Exception as exc:
            logger.debug("MetaTrader5 import failed: %s", exc)
            raise MT5UnavailableError(f"MetaTrader5 import failed: {exc}") from exc
        self._mt5 = mt5
        self._loaded = True

    # Lifecycle -----------------------------------------------------------
    def initialize(self, path: Optional[str] = None) -> bool:
        self._ensure_imported()
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
        self._ensure_imported()
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
        if not self._loaded or not self._mt5:
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
        if not self._loaded or not self._mt5:
            return None
        try:
            info = self._mt5.terminal_info()
            return info if info else None
        except Exception as exc:
            logger.debug("mt5.terminal_info() raised: %s", exc)
            return None

    def version(self) -> Optional[str]:
        if not self._loaded or not self._mt5:
            return None
        try:
            ver = self._mt5.version()
            return str(ver) if ver is not None else None
        except Exception as exc:
            logger.debug("mt5.version() raised: %s", exc)
            return None

    def last_error(self) -> Optional[Dict[str, Any]]:
        if not self._loaded or not self._mt5:
            return None
        try:
            last = self._mt5.last_error()
            return last if last else None
        except Exception as exc:
            logger.debug("mt5.last_error() raised: %s", exc)
            return None

    # Read-only data access ---------------------------------------------
    def account_info(self) -> Optional[Dict[str, Any]]:
        """
        Return account_info() as a dict or None.
        """
        if not self._loaded or not self._mt5:
            return None
        try:
            info = self._mt5.account_info()
            if not info:
                return None
            # Convert to dict if it's a namedtuple-like object
            try:
                return info._asdict()  # type: ignore[attr-defined]
            except Exception:
                # Fallback: attempt to cast to dict
                return dict(info) if isinstance(info, dict) else None
        except Exception as exc:
            logger.debug("mt5.account_info() raised: %s", exc)
            return None

    def positions_get(self) -> List[Dict[str, Any]]:
        """
        Return list of positions as dicts. Empty list on no positions or error.
        """
        if not self._loaded or not self._mt5:
            return []
        try:
            positions = self._mt5.positions_get()
            if not positions:
                return []
            out = []
            for p in positions:
                try:
                    out.append(p._asdict())  # type: ignore[attr-defined]
                except Exception:
                    out.append(dict(p) if isinstance(p, dict) else {})
            return out
        except Exception as exc:
            logger.debug("mt5.positions_get() raised: %s", exc)
            return []

    def symbols_get(self) -> List[Dict[str, Any]]:
        """
        Return list of available symbols as dicts.
        """
        if not self._loaded or not self._mt5:
            return []
        try:
            syms = self._mt5.symbols_get()
            if not syms:
                return []
            out = []
            for s in syms:
                try:
                    out.append(s._asdict())  # type: ignore[attr-defined]
                except Exception:
                    out.append(dict(s) if isinstance(s, dict) else {})
            return out
        except Exception as exc:
            logger.debug("mt5.symbols_get() raised: %s", exc)
            return []

    def symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Return symbol_info(symbol) as dict or None.
        """
        if not self._loaded or not self._mt5:
            return None
        try:
            info = self._mt5.symbol_info(symbol)
            if not info:
                return None
            try:
                return info._asdict()  # type: ignore[attr-defined]
            except Exception:
                return dict(info) if isinstance(info, dict) else None
        except Exception as exc:
            logger.debug("mt5.symbol_info(%s) raised: %s", symbol, exc)
            return None

    def symbol_info_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Return symbol_info_tick(symbol) as dict or None.
        """
        if not self._loaded or not self._mt5:
            return None
        try:
            tick = self._mt5.symbol_info_tick(symbol)
            if not tick:
                return None
            try:
                return tick._asdict()  # type: ignore[attr-defined]
            except Exception:
                return dict(tick) if isinstance(tick, dict) else None
        except Exception as exc:
            logger.debug("mt5.symbol_info_tick(%s) raised: %s", symbol, exc)
            return None

    def history_deals_get(self, from_dt: datetime.datetime, to_dt: datetime.datetime, ticket: Optional[int] = None, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Wrapper for mt5.history_deals_get. Returns list of deals as dicts.
        """
        if not self._loaded or not self._mt5:
            return []
        try:
            # mt5.history_deals_get accepts datetime objects in many builds
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
                try:
                    out.append(d._asdict())  # type: ignore[attr-defined]
                except Exception:
                    out.append(dict(d) if isinstance(d, dict) else {})
            return out
        except Exception as exc:
            logger.debug("mt5.history_deals_get() raised: %s", exc)
            return []

    def history_orders_get(self, from_dt: datetime.datetime, to_dt: datetime.datetime, ticket: Optional[int] = None, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Wrapper for mt5.history_orders_get. Returns list of orders as dicts.
        """
        if not self._loaded or not self._mt5:
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
                try:
                    out.append(o._asdict())  # type: ignore[attr-defined]
                except Exception:
                    out.append(dict(o) if isinstance(o, dict) else {})
            return out
        except Exception as exc:
            logger.debug("mt5.history_orders_get() raised: %s", exc)
            return []
