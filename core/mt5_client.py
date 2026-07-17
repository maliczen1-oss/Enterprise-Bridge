# core/mt5_client.py
"""
Thin wrapper around the MetaTrader5 Python bindings.

This module centralizes all direct imports and calls to the MetaTrader5
library so the rest of the codebase can be tested/mocked without importing
the real MT5 package.
"""
from typing import Any, Optional, Dict
import logging

logger = logging.getLogger("bridge")


class MT5UnavailableError(RuntimeError):
    pass


class MT5Client:
    def __init__(self):
        self._mt5 = None
        self._initialized = False
        self._loaded = False

    def _ensure_imported(self):
        if self._loaded:
            return
        try:
            import MetaTrader5 as mt5  # type: ignore
        except Exception as exc:
            logger.debug("MetaTrader5 import failed: %s", exc)
            raise MT5UnavailableError(f"MetaTrader5 import failed: {exc}") from exc
        self._mt5 = mt5
        self._loaded = True

    def initialize(self, path: Optional[str] = None) -> bool:
        """
        Initialize the MT5 terminal. Returns True on success, False otherwise.
        Raises MT5UnavailableError if the library cannot be imported.
        """
        self._ensure_imported()
        try:
            if path:
                # Some mt5 versions accept path positional arg, others accept named arg.
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
        Attempt to login. If login/password are None, assume the terminal
        is already connected (returns True).
        """
        self._ensure_imported()
        if not self._initialized:
            # Some setups allow login without explicit initialize; still attempt
            try:
                self._mt5.initialize()
                self._initialized = True
            except Exception:
                pass

        if login is None and password is None:
            # No credentials provided — assume already-running terminal is acceptable.
            return True

        try:
            if login is not None and password is not None and server:
                result = self._mt5.login(login, password, server)
            elif login is not None and password is not None:
                result = self._mt5.login(login, password)
            else:
                # insufficient credentials
                return False

            # Normalize result
            if isinstance(result, bool):
                return result
            if isinstance(result, (tuple, list)):
                return bool(result[0]) if result else False
            if isinstance(result, dict):
                # Some builds return dict-like status; treat retcode==0 as success
                return bool(result.get("retcode", 0) == 0)
            return bool(result)
        except Exception as exc:
            logger.debug("mt5.login() raised: %s", exc)
            return False

    def shutdown(self) -> bool:
        """
        Shutdown the MT5 terminal connection. Returns True on success.
        """
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

    def terminal_info(self) -> Optional[Dict[str, Any]]:
        """
        Return terminal_info() result or None.
        """
        if not self._loaded or not self._mt5:
            return None
        try:
            info = self._mt5.terminal_info()
            return info if info else None
        except Exception as exc:
            logger.debug("mt5.terminal_info() raised: %s", exc)
            return None

    def version(self) -> Optional[str]:
        """
        Return version() result as string or None.
        """
        if not self._loaded or not self._mt5:
            return None
        try:
            ver = self._mt5.version()
            return str(ver) if ver is not None else None
        except Exception as exc:
            logger.debug("mt5.version() raised: %s", exc)
            return None

    def last_error(self) -> Optional[Dict[str, Any]]:
        """
        Return last_error() result or None.
        """
        if not self._loaded or not self._mt5:
            return None
        try:
            last = self._mt5.last_error()
            return last if last else None
        except Exception as exc:
            logger.debug("mt5.last_error() raised: %s", exc)
            return None
