"""
ATLAS CERTIFICATION HEADER

name=core/mt5_client.py
Version: 4.0.0

Change Log
----------
- Replaced the Railway-incompatible local MetaTrader5 terminal dependency with
  a MetaApi REST backend when METAAPI_TOKEN and METAAPI_ACCOUNT_ID are present.
- Preserved the existing MT5Client public interface used by ConnectionManager
  and the read-only account, positions, symbols, market and history APIs.
- Preserved optional Windows MetaTrader5 fallback when MetaApi is not configured.
- Added MetaApi provisioning/account-region discovery so the client can use the
  correct MetaApi regional endpoint without requiring a new Railway variable.
- Added bounded HTTP timeouts, thread-safe HTTP access, structured last-error
  state and safe error sanitisation.
- Kept this module read-only: no MetaApi trade endpoint is exposed or invoked.

Production Certification: Atlas Phase 4.0
"""

from __future__ import annotations

import datetime
import logging
import os
import platform
import threading
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx


logger = logging.getLogger("bridge")


# ============================================================================
# Optional legacy Windows MetaTrader5 backend
# ============================================================================

try:
    import MetaTrader5 as mt5  # type: ignore

    _LOCAL_MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore
    _LOCAL_MT5_AVAILABLE = False


PLATFORM = platform.system().lower()

METAAPI_TOKEN = os.getenv("METAAPI_TOKEN", "").strip()
METAAPI_ACCOUNT_ID = os.getenv("METAAPI_ACCOUNT_ID", "").strip()

METAAPI_CONFIGURED = bool(
    METAAPI_TOKEN and METAAPI_ACCOUNT_ID
)

# Public compatibility constant retained from the previous implementation.
#
# MetaApi is considered the MT5 backend on Railway/Linux.
MT5_AVAILABLE = METAAPI_CONFIGURED or (
    _LOCAL_MT5_AVAILABLE and PLATFORM == "windows"
)


# ============================================================================
# Exceptions
# ============================================================================

class MT5UnavailableError(RuntimeError):
    """Raised when no supported MT5 backend is configured."""


class MetaApiError(RuntimeError):
    """Internal MetaApi transport/API error."""


# ============================================================================
# Configuration helpers
# ============================================================================

def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)

    if value is None or not value.strip():
        return default

    try:
        parsed = float(value)
        return parsed if parsed > 0 else default
    except (TypeError, ValueError):
        return default


def _metaapi_region_host(region: Optional[str]) -> str:
    """
    Build the MetaApi client API hostname for the account region.

    MetaApi currently exposes public regions such as:
        new-york
        london

    The generic construction also allows custom MetaApi regions.
    """
    normalized = (region or "new-york").strip().lower()
    normalized = normalized.replace("_", "-").replace(" ", "-")

    return (
        f"https://mt-client-api-v1."
        f"{normalized}.agiliumtrade.ai"
    )


def _provisioning_base_url() -> str:
    return os.getenv(
        "METAAPI_PROVISIONING_BASE_URL",
        "https://mt-provisioning-api-v1.agiliumtrade.ai",
    ).rstrip("/")


def _explicit_client_base_url() -> Optional[str]:
    value = os.getenv(
        "METAAPI_CLIENT_BASE_URL",
        "",
    ).strip()

    return value.rstrip("/") if value else None


def _as_dict(value: Any) -> Optional[Dict[str, Any]]:
    """Convert common MT5 response objects into dictionaries."""

    if value is None:
        return None

    if isinstance(value, dict):
        return dict(value)

    if hasattr(value, "_asdict"):
        try:
            return dict(value._asdict())
        except Exception:
            return None

    try:
        return dict(value)
    except Exception:
        return None


def _normalise_datetime(
    value: datetime.datetime,
) -> datetime.datetime:
    """
    Convert history boundaries to timezone-aware UTC.

    Naive datetimes are deliberately treated as UTC so Railway host timezone
    settings cannot alter historical queries.
    """

    if value.tzinfo is None:
        return value.replace(
            tzinfo=datetime.timezone.utc
        )

    return value.astimezone(
        datetime.timezone.utc
    )


def _iso_datetime(
    value: datetime.datetime,
) -> str:
    return (
        _normalise_datetime(value)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


# ============================================================================
# Capability model
# ============================================================================

def get_capabilities() -> Dict[str, Any]:
    """
    Return the runtime/backend capability model consumed by ConnectionManager.

    The previous implementation reported Linux as unsupported even when the
    application had valid MetaApi credentials. That made Railway permanently
    enter UNSUPPORTED_PLATFORM.

    MetaApi removes that platform restriction.
    """

    local_supported = PLATFORM == "windows"
    local_available = bool(
        _LOCAL_MT5_AVAILABLE and local_supported
    )

    if METAAPI_CONFIGURED:
        backend = "metaapi"
        supported = True
        available = True

    elif local_available:
        backend = "metatrader5"
        supported = True
        available = True

    else:
        backend = "disabled"
        supported = False
        available = False

    return {
        "platform": PLATFORM,
        "mt5Supported": supported,
        "mt5Available": available,
        "backend": backend,
        "backendType": backend,
        "metaApiConfigured": METAAPI_CONFIGURED,
        "metaApiTokenConfigured": bool(METAAPI_TOKEN),
        "metaApiAccountIdConfigured": bool(
            METAAPI_ACCOUNT_ID
        ),
        "metaApiRegion": None,
    }


# ============================================================================
# MT5Client
# ============================================================================

class MT5Client:
    """
    Compatibility wrapper used by ConnectionManager.

    Backend selection:

    1. MetaApi REST when METAAPI_TOKEN and METAAPI_ACCOUNT_ID are configured.
    2. Legacy MetaTrader5 Python bindings on supported Windows hosts when
       MetaApi is not configured.
    """

    def __init__(self) -> None:
        self._mt5 = (
            mt5 if _LOCAL_MT5_AVAILABLE else None
        )

        if METAAPI_CONFIGURED:
            self._backend = "metaapi"
        elif (
            _LOCAL_MT5_AVAILABLE
            and PLATFORM == "windows"
        ):
            self._backend = "metatrader5"
        else:
            self._backend = "disabled"

        self._initialized = False

        self._lock = threading.RLock()

        self._http: Optional[httpx.Client] = None

        self._client_base_url: Optional[str] = (
            _explicit_client_base_url()
        )

        self._region: Optional[str] = None

        self._account_metadata: Optional[
            Dict[str, Any]
        ] = None

        self._last_error: Optional[
            Dict[str, Any]
        ] = None

        self._timeout = _env_float(
            "METAAPI_TIMEOUT",
            _env_float(
                "REQUEST_TIMEOUT",
                15.0,
            ),
        )

        self._connect_timeout = min(
            self._timeout,
            10.0,
        )

    # ========================================================================
    # Backend helpers
    # ========================================================================

    @property
    def backend(self) -> str:
        return self._backend

    def _use_legacy(self) -> bool:
        return (
            self._backend == "metatrader5"
            and self._mt5 is not None
        )

    def _ensure_http_client(self) -> httpx.Client:
        with self._lock:
            if self._http is None:
                timeout = httpx.Timeout(
                    timeout=self._timeout,
                    connect=self._connect_timeout,
                )

                self._http = httpx.Client(
                    timeout=timeout,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": (
                            "WealthBuilder-Bridge/4.0.0"
                        ),
                    },
                    follow_redirects=True,
                )

            return self._http

    def _metaapi_headers(self) -> Dict[str, str]:
        """
        MetaApi authentication uses the auth-token header.

        Never log this dictionary.
        """

        return {
            "auth-token": METAAPI_TOKEN,
            "Accept": "application/json",
            "User-Agent": (
                "WealthBuilder-Bridge/4.0.0"
            ),
        }

    def _set_error(
        self,
        code: str,
        message: str,
        *,
        status_code: Optional[int] = None,
        details: Any = None,
    ) -> None:
        """
        Store a sanitised error.

        Authentication credentials and passwords are deliberately removed.
        """

        safe_details: Any = None

        if isinstance(
            details,
            (
                str,
                int,
                float,
                bool,
            ),
        ):
            safe_details = details

        elif isinstance(details, dict):
            sensitive = {
                "token",
                "auth-token",
                "authorization",
                "password",
                "access_token",
                "refresh_token",
            }

            safe_details = {
                str(key): value
                for key, value in details.items()
                if str(key).lower()
                not in sensitive
            }

        self._last_error = {
            "code": str(code),
            "message": str(message)[:500],
            "statusCode": status_code,
            "details": safe_details,
        }

    def _clear_error(self) -> None:
        self._last_error = None

    # ========================================================================
    # MetaApi HTTP
    # ========================================================================

    def _request_metaapi(
        self,
        method: str,
        url: str,
        *,
        params: Optional[
            Dict[str, Any]
        ] = None,
    ) -> Any:
        """
        Execute a MetaApi REST request.

        HTTP/network failures are converted into MetaApiError and recorded
        through last_error(). Authentication tokens are never exposed.
        """

        client = self._ensure_http_client()

        try:
            response = client.request(
                method,
                url,
                params=params,
                headers=self._metaapi_headers(),
            )

        except httpx.TimeoutException as exc:
            self._set_error(
                "METAAPI_TIMEOUT",
                "MetaApi request timed out.",
            )

            raise MetaApiError(
                "MetaApi request timed out."
            ) from exc

        except httpx.RequestError as exc:
            self._set_error(
                "METAAPI_NETWORK_ERROR",
                "Unable to reach MetaApi.",
            )

            raise MetaApiError(
                "Unable to reach MetaApi."
            ) from exc

        if response.status_code >= 400:
            payload: Any = None

            try:
                payload = response.json()
            except ValueError:
                pass

            message = (
                "MetaApi request failed."
            )

            api_code = (
                f"HTTP_{response.status_code}"
            )

            details = None

            if isinstance(payload, dict):
                details = payload.get(
                    "details"
                )

                api_message = payload.get(
                    "message"
                )

                api_error = payload.get(
                    "error"
                )

                if (
                    isinstance(api_message, str)
                    and api_message.strip()
                ):
                    message = api_message.strip()

                elif (
                    isinstance(api_error, str)
                    and api_error.strip()
                ):
                    message = api_error.strip()

                if isinstance(
                    details,
                    str,
                ):
                    api_code = details

                elif isinstance(
                    details,
                    dict,
                ):
                    detail_code = details.get(
                        "code"
                    )

                    if detail_code:
                        api_code = str(
                            detail_code
                        )

            self._set_error(
                f"METAAPI_{api_code.upper()}",
                message,
                status_code=response.status_code,
                details=details,
            )

            raise MetaApiError(message)

        if response.status_code == 204:
            self._clear_error()
            return None

        try:
            payload = response.json()

        except ValueError as exc:
            self._set_error(
                "METAAPI_INVALID_RESPONSE",
                "MetaApi returned invalid JSON.",
                status_code=response.status_code,
            )

            raise MetaApiError(
                "MetaApi returned invalid JSON."
            ) from exc

        self._clear_error()

        return payload

    def _provisioning_account(
        self,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve the MetaApi trading-account record.

        This provides:
        - state
        - connectionStatus
        - region
        - broker/server
        - login
        - account type
        """

        if not METAAPI_CONFIGURED:
            return None

        url = (
            f"{_provisioning_base_url()}"
            f"/users/current/accounts/"
            f"{quote(METAAPI_ACCOUNT_ID, safe='')}"
        )

        payload = self._request_metaapi(
            "GET",
            url,
        )

        return (
            payload
            if isinstance(payload, dict)
            else None
        )

    def _refresh_account_metadata(
        self,
    ) -> Optional[Dict[str, Any]]:
        metadata = self._provisioning_account()

        if isinstance(
            metadata,
            dict,
        ):
            self._account_metadata = metadata

            region = metadata.get(
                "region"
            )

            if (
                isinstance(region, str)
                and region.strip()
            ):
                self._region = region.strip()

            if not self._client_base_url:
                self._client_base_url = (
                    _metaapi_region_host(
                        self._region
                    )
                )

        return metadata

    def _client_url(
        self,
        path: str,
    ) -> str:
        if not self._client_base_url:
            self._client_base_url = (
                _metaapi_region_host(
                    self._region
                )
            )

        return (
            f"{self._client_base_url.rstrip('/')}"
            f"{path}"
        )

    def _metaapi_get(
        self,
        path: str,
        *,
        params: Optional[
            Dict[str, Any]
        ] = None,
    ) -> Any:
        return self._request_metaapi(
            "GET",
            self._client_url(path),
            params=params,
        )

    # ========================================================================
    # Lifecycle
    # ========================================================================

    def initialize(
        self,
        path: Optional[str] = None,
    ) -> bool:
        """
        Initialize the selected backend.

        MetaApi initialization:
        - validates credentials/account ID
        - retrieves the account
        - discovers its region
        - verifies that the account is provisioned
        """

        with self._lock:

            if self._backend == "disabled":
                self._set_error(
                    "MT5_BACKEND_UNAVAILABLE",
                    (
                        "No supported MetaApi or "
                        "MetaTrader5 backend is configured."
                    ),
                )

                self._initialized = False
                return False

            # ----------------------------------------------------------------
            # MetaApi backend
            # ----------------------------------------------------------------

            if self._backend == "metaapi":
                try:
                    metadata = (
                        self._refresh_account_metadata()
                    )

                    if not metadata:
                        self._set_error(
                            "METAAPI_ACCOUNT_NOT_FOUND",
                            (
                                "MetaApi account could "
                                "not be retrieved."
                            ),
                        )

                        self._initialized = False
                        return False

                    state = str(
                        metadata.get(
                            "state",
                            "",
                        )
                    ).upper()

                    if state not in {
                        "",
                        "DEPLOYED",
                        "DRAFT",
                    }:
                        self._set_error(
                            "METAAPI_ACCOUNT_NOT_READY",
                            (
                                "MetaApi account is "
                                "not ready for use."
                            ),
                            details={
                                "state": state,
                                "connectionStatus": (
                                    metadata.get(
                                        "connectionStatus"
                                    )
                                ),
                            },
                        )

                        self._initialized = False
                        return False

                    self._initialized = True
                    self._clear_error()

                    return True

                except MetaApiError:
                    self._initialized = False
                    return False

                except Exception:
                    logger.exception(
                        "MetaApi initialization failed."
                    )

                    self._set_error(
                        "METAAPI_INITIALIZE_FAILED",
                        "MetaApi initialization failed.",
                    )

                    self._initialized = False
                    return False

            # ----------------------------------------------------------------
            # Legacy Windows MetaTrader5 backend
            # ----------------------------------------------------------------

            if self._use_legacy():
                try:
                    if path:
                        try:
                            result = (
                                self._mt5.initialize(
                                    path
                                )
                            )
                        except TypeError:
                            result = (
                                self._mt5.initialize(
                                    path=path
                                )
                            )
                    else:
                        result = (
                            self._mt5.initialize()
                        )

                    self._initialized = bool(
                        result
                    )

                    if self._initialized:
                        self._clear_error()
                    else:
                        self._set_error(
                            "MT5_INITIALIZE_FAILED",
                            (
                                "MetaTrader5 terminal "
                                "initialization failed."
                            ),
                        )

                    return self._initialized

                except Exception:
                    logger.debug(
                        "mt5.initialize() raised.",
                        exc_info=True,
                    )

                    self._set_error(
                        "MT5_INITIALIZE_EXCEPTION",
                        (
                            "MetaTrader5 terminal "
                            "initialization failed."
                        ),
                    )

                    self._initialized = False

                    return False

            return False

    def login(
        self,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
    ) -> bool:
        """
        Establish backend readiness.

        For MetaApi, login/password/server are deliberately ignored because
        authentication is performed using METAAPI_TOKEN and
        METAAPI_ACCOUNT_ID.
        """

        with self._lock:

            # ----------------------------------------------------------------
            # MetaApi
            # ----------------------------------------------------------------

            if self._backend == "metaapi":

                if (
                    not self._initialized
                    and not self.initialize()
                ):
                    return False

                try:
                    metadata = (
                        self._refresh_account_metadata()
                    )

                    if not metadata:
                        return False

                    connection_status = str(
                        metadata.get(
                            "connectionStatus",
                            "",
                        )
                    ).upper()

                    if connection_status != "CONNECTED":
                        self._set_error(
                            "METAAPI_ACCOUNT_NOT_CONNECTED",
                            (
                                "MetaApi account is not "
                                "connected to the broker."
                            ),
                            details={
                                "connectionStatus": (
                                    connection_status
                                ),
                                "state": metadata.get(
                                    "state"
                                ),
                                "region": metadata.get(
                                    "region"
                                ),
                            },
                        )

                        return False

                    account = self._metaapi_get(
                        (
                            f"/users/current/accounts/"
                            f"{quote(METAAPI_ACCOUNT_ID, safe='')}"
                            f"/account-information"
                        )
                    )

                    if not isinstance(
                        account,
                        dict,
                    ):
                        self._set_error(
                            "METAAPI_ACCOUNT_INFO_INVALID",
                            (
                                "MetaApi returned an "
                                "invalid account-information "
                                "response."
                            ),
                        )

                        return False

                    self._initialized = True
                    self._clear_error()

                    return True

                except MetaApiError:
                    return False

                except Exception:
                    logger.exception(
                        "MetaApi readiness check failed."
                    )

                    self._set_error(
                        "METAAPI_LOGIN_FAILED",
                        (
                            "MetaApi account readiness "
                            "check failed."
                        ),
                    )

                    return False

            # ----------------------------------------------------------------
            # Legacy MetaTrader5
            # ----------------------------------------------------------------

            if not self._use_legacy():
                self._set_error(
                    "MT5_BACKEND_UNAVAILABLE",
                    (
                        "No supported MT5 backend "
                        "is configured."
                    ),
                )

                return False

            if not self._initialized:

                try:
                    if not self._mt5.initialize():
                        self._set_error(
                            "MT5_INITIALIZE_FAILED",
                            (
                                "MetaTrader5 terminal "
                                "initialization failed."
                            ),
                        )

                        return False

                    self._initialized = True

                except Exception:
                    self._set_error(
                        "MT5_INITIALIZE_EXCEPTION",
                        (
                            "MetaTrader5 terminal "
                            "initialization failed."
                        ),
                    )

                    return False

            if (
                login is None
                and password is None
            ):
                self._clear_error()
                return True

            try:

                if (
                    login is not None
                    and password is not None
                    and server
                ):
                    result = self._mt5.login(
                        login,
                        password,
                        server,
                    )

                elif (
                    login is not None
                    and password is not None
                ):
                    result = self._mt5.login(
                        login,
                        password,
                    )

                else:
                    self._set_error(
                        "MT5_LOGIN_INVALID",
                        (
                            "Incomplete MetaTrader5 "
                            "login configuration."
                        ),
                    )

                    return False

                if isinstance(
                    result,
                    bool,
                ):
                    success = result

                elif isinstance(
                    result,
                    (tuple, list),
                ):
                    success = (
                        bool(result[0])
                        if result
                        else False
                    )

                elif isinstance(
                    result,
                    dict,
                ):
                    success = bool(
                        result.get(
                            "retcode",
                            0,
                        )
                        == 0
                    )

                else:
                    success = bool(result)

                if success:
                    self._clear_error()
                else:
                    self._set_error(
                        "MT5_LOGIN_FAILED",
                        "MetaTrader5 login failed.",
                    )

                return success

            except Exception:
                logger.debug(
                    "mt5.login() raised.",
                    exc_info=True,
                )

                self._set_error(
                    "MT5_LOGIN_EXCEPTION",
                    "MetaTrader5 login failed.",
                )

                return False

    def shutdown(self) -> bool:
        """
        Shutdown the selected backend.

        MetaApi is a remote cloud service, so shutdown closes the local HTTP
        client and clears local lifecycle state rather than attempting to
        undeploy/delete the trading account.
        """

        with self._lock:

            if self._backend == "metaapi":

                self._initialized = False
                self._account_metadata = None
                self._region = None
                self._last_error = None

                if self._http is not None:
                    try:
                        self._http.close()
                    except Exception:
                        logger.debug(
                            "Failed to close MetaApi HTTP client.",
                            exc_info=True,
                        )
                    finally:
                        self._http = None

                return True

            if not self._use_legacy():
                self._initialized = False
                return True

            try:
                result = self._mt5.shutdown()

                self._initialized = False

                return (
                    bool(result)
                    if result is not None
                    else True
                )

            except Exception:
                logger.debug(
                    "mt5.shutdown() raised.",
                    exc_info=True,
                )

                self._initialized = False

                self._set_error(
                    "MT5_SHUTDOWN_FAILED",
                    (
                        "MetaTrader5 shutdown "
                        "failed."
                    ),
                )

                return False

    # ========================================================================
    # Introspection
    # ========================================================================

    def terminal_info(
        self,
    ) -> Optional[Dict[str, Any]]:

        if self._backend == "metaapi":

            metadata = (
                self._account_metadata
            )

            if metadata is None:
                try:
                    metadata = (
                        self._refresh_account_metadata()
                    )
                except MetaApiError:
                    return None

            if not metadata:
                return None

            return {
                "backend": "metaapi",
                "accountId": METAAPI_ACCOUNT_ID,
                "state": metadata.get(
                    "state"
                ),
                "connectionStatus": metadata.get(
                    "connectionStatus"
                ),
                "region": metadata.get(
                    "region"
                ),
                "type": metadata.get(
                    "type"
                ),
                "server": metadata.get(
                    "server"
                ),
                "login": metadata.get(
                    "login"
                ),
                "baseCurrency": metadata.get(
                    "baseCurrency"
                ),
                "reliability": metadata.get(
                    "reliability"
                ),
                "manualTrades": metadata.get(
                    "manualTrades"
                ),
                "primaryReplica": metadata.get(
                    "primaryReplica"
                ),
            }

        if not self._use_legacy():
            return None

        try:
            return _as_dict(
                self._mt5.terminal_info()
            )
        except Exception:
            logger.debug(
                "mt5.terminal_info() raised.",
                exc_info=True,
            )
            return None

    def version(self) -> Optional[str]:

        if self._backend == "metaapi":
            return "MetaApi REST"

        if not self._use_legacy():
            return None

        try:
            version = self._mt5.version()

            return (
                str(version)
                if version is not None
                else None
            )

        except Exception:
            logger.debug(
                "mt5.version() raised.",
                exc_info=True,
            )
            return None

    def last_error(
        self,
    ) -> Optional[Dict[str, Any]]:

        if self._backend == "metaapi":
            return (
                dict(self._last_error)
                if self._last_error
                else None
            )

        if not self._use_legacy():
            return None

        try:
            last = self._mt5.last_error()

            if isinstance(
                last,
                dict,
            ):
                return dict(last)

            converted = _as_dict(last)

            if converted is not None:
                return converted

            return (
                {"error": str(last)}
                if last is not None
                else None
            )

        except Exception:
            logger.debug(
                "mt5.last_error() raised.",
                exc_info=True,
            )
            return None

    # ========================================================================
    # Account
    # ========================================================================

    def account_info(
        self,
    ) -> Optional[Dict[str, Any]]:

        if self._backend == "metaapi":

            try:
                account = self._metaapi_get(
                    (
                        f"/users/current/accounts/"
                        f"{quote(METAAPI_ACCOUNT_ID, safe='')}"
                        f"/account-information"
                    )
                )

                if isinstance(
                    account,
                    dict,
                ):
                    return account

                self._set_error(
                    "METAAPI_ACCOUNT_INFO_INVALID",
                    (
                        "MetaApi returned an "
                        "invalid account-information "
                        "response."
                    ),
                )

                return None

            except MetaApiError:
                return None

        if not self._use_legacy():
            return None

        try:
            return _as_dict(
                self._mt5.account_info()
            )

        except Exception:
            logger.debug(
                "mt5.account_info() raised.",
                exc_info=True,
            )

            return None

    # ========================================================================
    # Positions
    # ========================================================================

    def positions_get(
        self,
    ) -> List[Dict[str, Any]]:

        if self._backend == "metaapi":

            try:
                positions = self._metaapi_get(
                    (
                        f"/users/current/accounts/"
                        f"{quote(METAAPI_ACCOUNT_ID, safe='')}"
                        f"/positions"
                    )
                )

                if not positions:
                    return []

                if isinstance(
                    positions,
                    list,
                ):
                    return [
                        dict(position)
                        for position in positions
                        if isinstance(
                            position,
                            dict,
                        )
                    ]

                self._set_error(
                    "METAAPI_POSITIONS_INVALID",
                    (
                        "MetaApi returned an "
                        "invalid positions response."
                    ),
                )

                return []

            except MetaApiError:
                return []

        if not self._use_legacy():
            return []

        try:
            positions = (
                self._mt5.positions_get()
            )

            if not positions:
                return []

            return [
                _as_dict(position) or {}
                for position in positions
            ]

        except Exception:
            logger.debug(
                "mt5.positions_get() raised.",
                exc_info=True,
            )
            return []

    # ========================================================================
    # Symbols
    # ========================================================================

    def symbols_get(
        self,
    ) -> List[Dict[str, Any]]:

        if self._backend == "metaapi":

            try:
                symbols = self._metaapi_get(
                    (
                        f"/users/current/accounts/"
                        f"{quote(METAAPI_ACCOUNT_ID, safe='')}"
                        f"/symbols"
                    )
                )

                if not symbols:
                    return []

                if isinstance(
                    symbols,
                    list,
                ):
                    # Preserve the previous MT5Client return type:
                    # list[dict].
                    #
                    # The exact broker symbol is never rewritten.
                    return [
                        {
                            "name": str(symbol),
                            "symbol": str(symbol),
                        }
                        for symbol in symbols
                        if (
                            isinstance(
                                symbol,
                                str,
                            )
                            and symbol.strip()
                        )
                    ]

                self._set_error(
                    "METAAPI_SYMBOLS_INVALID",
                    (
                        "MetaApi returned an "
                        "invalid symbols response."
                    ),
                )

                return []

            except MetaApiError:
                return []

        if not self._use_legacy():
            return []

        try:
            symbols = (
                self._mt5.symbols_get()
            )

            if not symbols:
                return []

            return [
                _as_dict(symbol) or {}
                for symbol in symbols
            ]

        except Exception:
            logger.debug(
                "mt5.symbols_get() raised.",
                exc_info=True,
            )

            return []

    # ========================================================================
    # Symbol specification
    # ========================================================================

    def symbol_info(
        self,
        symbol: str,
    ) -> Optional[Dict[str, Any]]:

        if (
            not isinstance(symbol, str)
            or not symbol.strip()
        ):
            self._set_error(
                "INVALID_SYMBOL",
                (
                    "Symbol must be a "
                    "non-empty string."
                ),
            )

            return None

        symbol = symbol.strip()

        if self._backend == "metaapi":

            try:
                encoded_symbol = quote(
                    symbol,
                    safe="",
                )

                specification = (
                    self._metaapi_get(
                        (
                            f"/users/current/accounts/"
                            f"{quote(METAAPI_ACCOUNT_ID, safe='')}"
                            f"/symbols/{encoded_symbol}"
                            f"/specification"
                        )
                    )
                )

                if isinstance(
                    specification,
                    dict,
                ):
                    specification.setdefault(
                        "symbol",
                        symbol,
                    )

                    specification.setdefault(
                        "name",
                        symbol,
                    )

                    return specification

                self._set_error(
                    "METAAPI_SYMBOL_INFO_INVALID",
                    (
                        "MetaApi returned an "
                        "invalid symbol specification."
                    ),
                )

                return None

            except MetaApiError:
                return None

        if not self._use_legacy():
            return None

        try:
            return _as_dict(
                self._mt5.symbol_info(symbol)
            )

        except Exception:
            logger.debug(
                "mt5.symbol_info() raised.",
                exc_info=True,
            )

            return None

    # ========================================================================
    # Current tick
    # ========================================================================

    def symbol_info_tick(
        self,
        symbol: str,
    ) -> Optional[Dict[str, Any]]:

        if (
            not isinstance(symbol, str)
            or not symbol.strip()
        ):
            self._set_error(
                "INVALID_SYMBOL",
                (
                    "Symbol must be a "
                    "non-empty string."
                ),
            )

            return None

        symbol = symbol.strip()

        if self._backend == "metaapi":

            try:
                encoded_symbol = quote(
                    symbol,
                    safe="",
                )

                tick = self._metaapi_get(
                    (
                        f"/users/current/accounts/"
                        f"{quote(METAAPI_ACCOUNT_ID, safe='')}"
                        f"/symbols/{encoded_symbol}"
                        f"/current-tick"
                    )
                )

                if isinstance(
                    tick,
                    dict,
                ):
                    tick.setdefault(
                        "symbol",
                        symbol,
                    )

                    return tick

                self._set_error(
                    "METAAPI_SYMBOL_TICK_INVALID",
                    (
                        "MetaApi returned an "
                        "invalid symbol tick."
                    ),
                )

                return None

            except MetaApiError:
                return None

        if not self._use_legacy():
            return None

        try:
            return _as_dict(
                self._mt5.symbol_info_tick(
                    symbol
                )
            )

        except Exception:
            logger.debug(
                "mt5.symbol_info_tick() raised.",
                exc_info=True,
            )

            return None

    # ========================================================================
    # History: deals
    # ========================================================================

    def history_deals_get(
        self,
        from_dt: datetime.datetime,
        to_dt: datetime.datetime,
        ticket: Optional[int] = None,
        symbol: Optional[str] = None,
    ) -> List[Dict[str, Any]]:

        if self._backend == "metaapi":

            try:
                account_id = quote(
                    METAAPI_ACCOUNT_ID,
                    safe="",
                )

                # Direct ticket lookup is cheaper and more precise.
                if ticket is not None:
                    path = (
                        f"/users/current/accounts/"
                        f"{account_id}"
                        f"/history-deals/ticket/"
                        f"{quote(str(ticket), safe='')}"
                    )

                    deals = self._metaapi_get(
                        path
                    )

                else:
                    start = quote(
                        _iso_datetime(from_dt),
                        safe="",
                    )

                    end = quote(
                        _iso_datetime(to_dt),
                        safe="",
                    )

                    path = (
                        f"/users/current/accounts/"
                        f"{account_id}"
                        f"/history-deals/time/"
                        f"{start}/{end}"
                    )

                    deals = self._metaapi_get(
                        path,
                        params={
                            "limit": 1000,
                            "offset": 0,
                        },
                    )

                if not isinstance(
                    deals,
                    list,
                ):
                    self._set_error(
                        "METAAPI_HISTORY_DEALS_INVALID",
                        (
                            "MetaApi returned an "
                            "invalid history-deals response."
                        ),
                    )

                    return []

                result = [
                    dict(deal)
                    for deal in deals
                    if isinstance(
                        deal,
                        dict,
                    )
                ]

                if symbol:
                    wanted = symbol.strip().upper()

                    result = [
                        deal
                        for deal in result
                        if str(
                            deal.get(
                                "symbol",
                                "",
                            )
                        ).upper() == wanted
                    ]

                return result

            except MetaApiError:
                return []

        if not self._use_legacy():
            return []

        try:
            if ticket is not None:
                deals = (
                    self._mt5.history_deals_get(
                        from_dt,
                        to_dt,
                        ticket,
                    )
                )

            elif symbol:
                deals = (
                    self._mt5.history_deals_get(
                        from_dt,
                        to_dt,
                        symbol,
                    )
                )

            else:
                deals = (
                    self._mt5.history_deals_get(
                        from_dt,
                        to_dt,
                    )
                )

            if not deals:
                return []

            return [
                _as_dict(deal) or {}
                for deal in deals
            ]

        except Exception:
            logger.debug(
                "mt5.history_deals_get() raised.",
                exc_info=True,
            )

            return []

    # ========================================================================
    # History: orders
    # ========================================================================

    def history_orders_get(
        self,
        from_dt: datetime.datetime,
        to_dt: datetime.datetime,
        ticket: Optional[int] = None,
        symbol: Optional[str] = None,
    ) -> List[Dict[str, Any]]:

        if self._backend == "metaapi":

            try:
                account_id = quote(
                    METAAPI_ACCOUNT_ID,
                    safe="",
                )

                if ticket is not None:
                    path = (
                        f"/users/current/accounts/"
                        f"{account_id}"
                        f"/history-orders/ticket/"
                        f"{quote(str(ticket), safe='')}"
                    )

                    orders = self._metaapi_get(
                        path
                    )

                else:
                    start = quote(
                        _iso_datetime(from_dt),
                        safe="",
                    )

                    end = quote(
                        _iso_datetime(to_dt),
                        safe="",
                    )

                    path = (
                        f"/users/current/accounts/"
                        f"{account_id}"
                        f"/history-orders/time/"
                        f"{start}/{end}"
                    )

                    orders = self._metaapi_get(
                        path,
                        params={
                            "limit": 1000,
                            "offset": 0,
                        },
                    )

                if not isinstance(
                    orders,
                    list,
                ):
                    self._set_error(
                        "METAAPI_HISTORY_ORDERS_INVALID",
                        (
                            "MetaApi returned an "
                            "invalid history-orders response."
                        ),
                    )

                    return []

                result = [
                    dict(order)
                    for order in orders
                    if isinstance(
                        order,
                        dict,
                    )
                ]

                if symbol:
                    wanted = symbol.strip().upper()

                    result = [
                        order
                        for order in result
                        if str(
                            order.get(
                                "symbol",
                                "",
                            )
                        ).upper() == wanted
                    ]

                return result

            except MetaApiError:
                return []

        if not self._use_legacy():
            return []

        try:

            if ticket is not None:
                orders = (
                    self._mt5.history_orders_get(
                        from_dt,
                        to_dt,
                        ticket,
                    )
                )

            elif symbol:
                orders = (
                    self._mt5.history_orders_get(
                        from_dt,
                        to_dt,
                        symbol,
                    )
                )

            else:
                orders = (
                    self._mt5.history_orders_get(
                        from_dt,
                        to_dt,
                    )
                )

            if not orders:
                return []

            return [
                _as_dict(order) or {}
                for order in orders
            ]

        except Exception:
            logger.debug(
                "mt5.history_orders_get() raised.",
                exc_info=True,
            )

            return []
