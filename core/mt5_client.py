"""
ATLAS CERTIFICATION HEADER

name=core/mt5_client.py
version=4.0.3
certification=ATLAS
status=PRODUCTION-READY

Purpose
-------
Production MetaApi / MetaTrader5 compatibility client for Enterprise Bridge.

Version 4.0.3
-------------
- Corrects the MetaApi Provisioning API hostname.
- Uses:
    https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai
- Preserves configurable METAAPI_PROVISIONING_BASE_URL override.
- Preserves safe DNS diagnostics.
- Preserves transport diagnostics.
- Preserves credential redaction.
- Preserves retry handling.
- Preserves Railway compatibility.
- Preserves MetaApi / legacy Windows MetaTrader5 compatibility.
- Does not modify readiness/lifecycle state handling.
- Does not modify MetaApi credentials.
- Does not modify API routes.
"""

from __future__ import annotations

import datetime
import logging
import os
import platform
import socket
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse

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


# ============================================================================
# MetaApi configuration
# ============================================================================

METAAPI_TOKEN = os.getenv(
    "METAAPI_TOKEN",
    "",
).strip()

METAAPI_ACCOUNT_ID = os.getenv(
    "METAAPI_ACCOUNT_ID",
    "",
).strip()

METAAPI_CONFIGURED = bool(
    METAAPI_TOKEN
    and METAAPI_ACCOUNT_ID
)

MT5_AVAILABLE = (
    METAAPI_CONFIGURED
    or (
        _LOCAL_MT5_AVAILABLE
        and PLATFORM == "windows"
    )
)


# ============================================================================
# Exceptions
# ============================================================================

class MT5UnavailableError(RuntimeError):
    """Raised when no supported MT5 backend is configured."""


class MetaApiError(RuntimeError):
    """Internal MetaApi transport/API error."""


# ============================================================================
# Environment helpers
# ============================================================================

def _env_float(
    name: str,
    default: float,
) -> float:
    value = os.getenv(name)

    if value is None or not value.strip():
        return default

    try:
        parsed = float(value)

        if parsed > 0:
            return parsed

    except (TypeError, ValueError):
        pass

    return default


def _env_int(
    name: str,
    default: int,
    minimum: int = 0,
    maximum: int = 10,
) -> int:
    value = os.getenv(name)

    if value is None or not value.strip():
        return default

    try:
        parsed = int(value)

        if minimum <= parsed <= maximum:
            return parsed

    except (TypeError, ValueError):
        pass

    return default


def _provisioning_base_url() -> str:
    """
    Return the MetaApi Provisioning API endpoint.

    The hostname was externally verified on 2026-08-12.

    Verified hostname:
        mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai

    The environment variable remains available so deployments can
    explicitly override the endpoint if MetaApi changes its API topology.
    """

    return (
        os.getenv(
            "METAAPI_PROVISIONING_BASE_URL",
            "https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai",
        )
        .strip()
        .rstrip("/")
    )


def _explicit_client_base_url() -> Optional[str]:
    value = os.getenv(
        "METAAPI_CLIENT_BASE_URL",
        "",
    ).strip()

    if not value:
        return None

    return value.rstrip("/")


def _metaapi_region_host(
    region: Optional[str],
) -> str:
    normalized = (
        region or "new-york"
    ).strip().lower()

    normalized = (
        normalized
        .replace("_", "-")
        .replace(" ", "-")
    )

    return (
        "https://mt-client-api-v1."
        f"{normalized}.agiliumtrade.ai"
    )


def _as_dict(
    value: Any,
) -> Optional[Dict[str, Any]]:
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
# Safe credential redaction
# ============================================================================

def _redact_sensitive_text(
    value: Any,
) -> str:
    """
    Never expose:

    - METAAPI_TOKEN
    - METAAPI_ACCOUNT_ID
    - authorization headers
    - passwords
    - API keys
    - secrets
    """

    text = str(value)

    sensitive_values = (
        METAAPI_TOKEN,
        METAAPI_ACCOUNT_ID,
    )

    for sensitive in sensitive_values:
        if sensitive:
            text = text.replace(
                sensitive,
                "[REDACTED]",
            )

    markers = (
        "Authorization:",
        "authorization:",
        "auth-token:",
        "Auth-Token:",
        "token=",
        "access_token=",
        "refresh_token=",
        "password=",
        "secret=",
        "api_key=",
        "apikey=",
    )

    for marker in markers:
        if marker in text:

            prefix, _, remainder = (
                text.partition(marker)
            )

            if remainder:
                separator = ""

                if remainder.startswith(" "):
                    separator = " "

                elif remainder.startswith("="):
                    separator = "="

                text = (
                    prefix
                    + marker
                    + separator
                    + "[REDACTED]"
                )

    return text[:1000]


# ============================================================================
# Safe URL diagnostics
# ============================================================================

def _safe_hostname(
    url: str,
) -> Optional[str]:
    try:
        return urlparse(url).hostname
    except Exception:
        return None


def _safe_scheme(
    url: str,
) -> Optional[str]:
    try:
        return (
            urlparse(url)
            .scheme
            .lower()
            or None
        )
    except Exception:
        return None


def _safe_port(
    url: str,
) -> Optional[int]:
    try:
        parsed = urlparse(url)

        if parsed.port is not None:
            return parsed.port

        if parsed.scheme.lower() == "https":
            return 443

        if parsed.scheme.lower() == "http":
            return 80

    except Exception:
        pass

    return None


def _exception_errno(
    exc: BaseException,
) -> Any:
    errno_value = getattr(
        exc,
        "errno",
        None,
    )

    if errno_value is not None:
        return errno_value

    args = getattr(
        exc,
        "args",
        (),
    )

    if args and isinstance(args[0], int):
        return args[0]

    return None


def _exception_chain(
    exc: BaseException,
) -> List[BaseException]:

    chain: List[BaseException] = []

    current: Optional[
        BaseException
    ] = exc

    visited: set[int] = set()

    while (
        current is not None
        and len(chain) < 6
    ):
        identifier = id(current)

        if identifier in visited:
            break

        visited.add(identifier)
        chain.append(current)

        cause = getattr(
            current,
            "__cause__",
            None,
        )

        if cause is not None:
            current = cause
            continue

        context = getattr(
            current,
            "__context__",
            None,
        )

        if context is not None:
            current = context
            continue

        break

    return chain


# ============================================================================
# DNS diagnostics
# ============================================================================

def _resolve_hostname(
    hostname: Optional[str],
    port: Optional[int],
) -> Dict[str, Any]:
    """
    Safely resolve a hostname using the container's system resolver.

    No credentials or credential-bearing URLs are involved.
    """

    result: Dict[str, Any] = {
        "hostname": hostname,
        "port": port,
        "resolved": False,
        "addresses": [],
    }

    if not hostname:
        result.update(
            {
                "resolverException": (
                    "InvalidHostname"
                ),
                "resolverReason": (
                    "No hostname could be extracted."
                ),
            }
        )

        return result

    target_port = port or 443

    try:
        records = socket.getaddrinfo(
            hostname,
            target_port,
            type=socket.SOCK_STREAM,
        )

        addresses: List[str] = []

        for record in records:
            sockaddr = record[4]

            if not sockaddr:
                continue

            address = sockaddr[0]

            if address not in addresses:
                addresses.append(address)

        result["resolved"] = bool(addresses)
        result["addresses"] = addresses[:10]

        if not addresses:
            result["resolverException"] = (
                "NoAddresses"
            )

            result["resolverReason"] = (
                "Resolver returned no usable addresses."
            )

    except socket.gaierror as exc:
        result["resolverException"] = (
            type(exc).__name__
        )

        result["resolverErrno"] = (
            getattr(
                exc,
                "errno",
                None,
            )
        )

        result["resolverReason"] = (
            _redact_sensitive_text(exc)
        )

    except Exception as exc:
        result["resolverException"] = (
            type(exc).__name__
        )

        result["resolverErrno"] = (
            _exception_errno(exc)
        )

        result["resolverReason"] = (
            _redact_sensitive_text(exc)
        )

    return result


def _build_transport_diagnostics(
    url: str,
    exc: BaseException,
    attempt: int,
    attempts: int,
) -> Dict[str, Any]:

    hostname = _safe_hostname(url)
    scheme = _safe_scheme(url)
    port = _safe_port(url)

    diagnostics: Dict[str, Any] = {
        "host": hostname,
        "scheme": scheme,
        "port": port,
        "exception": type(exc).__name__,
        "attempt": attempt,
        "attempts": attempts,
        "reason": _redact_sensitive_text(exc),
    }

    errno_value = _exception_errno(exc)

    if errno_value is not None:
        diagnostics["errno"] = errno_value

    dns = _resolve_hostname(
        hostname,
        port,
    )

    diagnostics["dns"] = dns

    chain = _exception_chain(exc)

    if len(chain) > 1:

        causes: List[
            Dict[str, Any]
        ] = []

        for index, item in enumerate(
            chain[1:],
            start=1,
        ):

            cause: Dict[
                str,
                Any,
            ] = {
                "depth": index,
                "exception": (
                    type(item).__name__
                ),
                "reason": (
                    _redact_sensitive_text(
                        item
                    )
                ),
            }

            cause_errno = _exception_errno(
                item
            )

            if cause_errno is not None:
                cause["errno"] = cause_errno

            causes.append(cause)

        diagnostics["causeChain"] = causes

    return diagnostics


# ============================================================================
# Capabilities
# ============================================================================

def get_capabilities() -> Dict[str, Any]:

    local_supported = (
        PLATFORM == "windows"
    )

    local_available = bool(
        _LOCAL_MT5_AVAILABLE
        and local_supported
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
        "metaApiConfigured": (
            METAAPI_CONFIGURED
        ),
        "metaApiTokenConfigured": bool(
            METAAPI_TOKEN
        ),
        "metaApiAccountIdConfigured": bool(
            METAAPI_ACCOUNT_ID
        ),
        "metaApiRegion": None,
    }


# ============================================================================
# MT5Client
# ============================================================================

class MT5Client:

    def __init__(
        self,
    ) -> None:

        self._mt5 = (
            mt5
            if _LOCAL_MT5_AVAILABLE
            else None
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

        self._http: Optional[
            httpx.Client
        ] = None

        self._client_base_url = (
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

        self._retry_count = _env_int(
            "METAAPI_RETRY_COUNT",
            3,
            minimum=0,
            maximum=5,
        )

        self._retry_delay = _env_float(
            "METAAPI_RETRY_DELAY",
            0.75,
        )

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def initialized(self) -> bool:
        return self._initialized

    def _use_legacy(self) -> bool:
        return bool(
            self._backend == "metatrader5"
            and self._mt5 is not None
        )

    # ========================================================================
    # HTTP client
    # ========================================================================

    def _ensure_http_client(
        self,
    ) -> httpx.Client:

        with self._lock:

            if self._http is None:

                timeout = httpx.Timeout(
                    timeout=self._timeout,
                    connect=self._connect_timeout,
                )

                # Deliberately allow normal Railway/container
                # environment and proxy configuration.
                self._http = httpx.Client(
                    timeout=timeout,
                    headers={
                        "Accept": (
                            "application/json"
                        ),
                        "User-Agent": (
                            "WealthBuilder-Bridge/"
                            "4.0.3"
                        ),
                    },
                    follow_redirects=True,
                )

            return self._http

    # ========================================================================
    # Authentication
    # ========================================================================

    def _metaapi_headers(
        self,
    ) -> Dict[str, str]:

        return {
            "auth-token": METAAPI_TOKEN,
            "Accept": "application/json",
            "User-Agent": (
                "WealthBuilder-Bridge/"
                "4.0.3"
            ),
        }

    # ========================================================================
    # Error state
    # ========================================================================

    def _set_error(
        self,
        code: str,
        message: str,
        *,
        status_code: Optional[int] = None,
        details: Any = None,
    ) -> None:

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

        elif isinstance(
            details,
            dict,
        ):

            blocked = {
                "token",
                "auth-token",
                "authorization",
                "password",
                "access_token",
                "refresh_token",
                "secret",
                "api_key",
                "apikey",
            }

            safe_details = {}

            for key, value in details.items():

                normalized = (
                    str(key)
                    .strip()
                    .lower()
                )

                if normalized in blocked:
                    continue

                safe_details[str(key)] = value

        self._last_error = {
            "code": str(code),
            "message": str(message)[:500],
            "statusCode": status_code,
            "details": safe_details,
        }

    def _clear_error(self) -> None:
        self._last_error = None

    # ========================================================================
    # MetaApi request
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

        client = (
            self._ensure_http_client()
        )

        attempts = (
            self._retry_count + 1
        )

        last_exception: Optional[
            BaseException
        ] = None

        for attempt_index in range(
            attempts
        ):

            attempt = (
                attempt_index + 1
            )

            try:

                response = client.request(
                    method,
                    url,
                    params=params,
                    headers=self._metaapi_headers(),
                )

                break

            except httpx.TimeoutException as exc:

                last_exception = exc

                diagnostics = (
                    _build_transport_diagnostics(
                        url,
                        exc,
                        attempt,
                        attempts,
                    )
                )

                self._set_error(
                    "METAAPI_TIMEOUT",
                    "MetaApi request timed out.",
                    details=diagnostics,
                )

                logger.error(
                    "MetaApi transport timeout: "
                    "host=%s scheme=%s port=%s "
                    "exception=%s attempt=%s/%s "
                    "errno=%s reason=%s dns=%s",
                    diagnostics.get("host"),
                    diagnostics.get("scheme"),
                    diagnostics.get("port"),
                    diagnostics.get("exception"),
                    diagnostics.get("attempt"),
                    diagnostics.get("attempts"),
                    diagnostics.get("errno"),
                    diagnostics.get("reason"),
                    diagnostics.get("dns"),
                )

                if attempt < attempts:

                    delay = (
                        self._retry_delay
                        * (2 ** attempt_index)
                    )

                    logger.warning(
                        "Retrying MetaApi timeout: "
                        "nextAttempt=%s/%s "
                        "delay=%.2fs",
                        attempt + 1,
                        attempts,
                        delay,
                    )

                    time.sleep(delay)

                    continue

                raise MetaApiError(
                    "MetaApi request timed out."
                ) from exc

            except httpx.RequestError as exc:

                last_exception = exc

                diagnostics = (
                    _build_transport_diagnostics(
                        url,
                        exc,
                        attempt,
                        attempts,
                    )
                )

                self._set_error(
                    "METAAPI_NETWORK_ERROR",
                    "Unable to reach MetaApi.",
                    details=diagnostics,
                )

                logger.error(
                    "MetaApi transport error: "
                    "host=%s scheme=%s port=%s "
                    "exception=%s attempt=%s/%s "
                    "errno=%s reason=%s dns=%s",
                    diagnostics.get("host"),
                    diagnostics.get("scheme"),
                    diagnostics.get("port"),
                    diagnostics.get("exception"),
                    diagnostics.get("attempt"),
                    diagnostics.get("attempts"),
                    diagnostics.get("errno"),
                    diagnostics.get("reason"),
                    diagnostics.get("dns"),
                )

                cause_chain = (
                    diagnostics.get(
                        "causeChain"
                    )
                )

                if cause_chain:

                    logger.error(
                        "MetaApi underlying "
                        "transport cause chain: %s",
                        cause_chain,
                    )

                if attempt < attempts:

                    delay = (
                        self._retry_delay
                        * (2 ** attempt_index)
                    )

                    logger.warning(
                        "Retrying MetaApi network request: "
                        "nextAttempt=%s/%s "
                        "delay=%.2fs",
                        attempt + 1,
                        attempts,
                        delay,
                    )

                    time.sleep(delay)

                    continue

                raise MetaApiError(
                    "Unable to reach MetaApi."
                ) from exc

            except Exception as exc:

                last_exception = exc

                diagnostics = (
                    _build_transport_diagnostics(
                        url,
                        exc,
                        attempt,
                        attempts,
                    )
                )

                self._set_error(
                    "METAAPI_TRANSPORT_EXCEPTION",
                    "MetaApi transport failed.",
                    details=diagnostics,
                )

                logger.error(
                    "MetaApi unexpected transport exception: "
                    "host=%s scheme=%s port=%s "
                    "exception=%s attempt=%s/%s "
                    "errno=%s reason=%s dns=%s",
                    diagnostics.get("host"),
                    diagnostics.get("scheme"),
                    diagnostics.get("port"),
                    diagnostics.get("exception"),
                    diagnostics.get("attempt"),
                    diagnostics.get("attempts"),
                    diagnostics.get("errno"),
                    diagnostics.get("reason"),
                    diagnostics.get("dns"),
                )

                raise MetaApiError(
                    "MetaApi transport failed."
                ) from exc

        else:

            diagnostics = (
                _build_transport_diagnostics(
                    url,
                    last_exception
                    or RuntimeError(
                        "Unknown transport failure."
                    ),
                    attempts,
                    attempts,
                )
            )

            self._set_error(
                "METAAPI_NETWORK_ERROR",
                "Unable to reach MetaApi.",
                details=diagnostics,
            )

            raise MetaApiError(
                "Unable to reach MetaApi."
            ) from last_exception

        # =====================================================================
        # HTTP errors
        # =====================================================================

        if response.status_code >= 400:

            payload: Any = None

            try:
                payload = response.json()

            except ValueError:
                payload = None

            message = (
                "MetaApi request failed."
            )

            api_code = (
                f"HTTP_{response.status_code}"
            )

            details: Any = None

            if isinstance(
                payload,
                dict,
            ):

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
                    isinstance(
                        api_message,
                        str,
                    )
                    and api_message.strip()
                ):
                    message = (
                        api_message.strip()
                    )

                elif (
                    isinstance(
                        api_error,
                        str,
                    )
                    and api_error.strip()
                ):
                    message = (
                        api_error.strip()
                    )

                if isinstance(
                    details,
                    str,
                ):
                    api_code = details

                elif isinstance(
                    details,
                    dict,
                ):

                    detail_code = (
                        details.get("code")
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

            raise MetaApiError(
                message
            )

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

    # ========================================================================
    # Provisioning
    # ========================================================================

    def _provisioning_account(
        self,
    ) -> Optional[
        Dict[str, Any]
    ]:

        if not METAAPI_CONFIGURED:
            return None

        url = (
            f"{_provisioning_base_url()}"
            "/users/current/accounts/"
            f"{quote(METAAPI_ACCOUNT_ID, safe='')}"
        )

        payload = (
            self._request_metaapi(
                "GET",
                url,
            )
        )

        return (
            payload
            if isinstance(
                payload,
                dict,
            )
            else None
        )

    def _refresh_account_metadata(
        self,
    ) -> Optional[
        Dict[str, Any]
    ]:

        metadata = (
            self._provisioning_account()
        )

        if isinstance(
            metadata,
            dict,
        ):

            self._account_metadata = (
                metadata
            )

            region = metadata.get(
                "region"
            )

            if (
                isinstance(
                    region,
                    str,
                )
                and region.strip()
            ):
                self._region = (
                    region.strip()
                )

            if not self._client_base_url:

                self._client_base_url = (
                    _metaapi_region_host(
                        self._region
                    )
                )

        return metadata

    # ========================================================================
    # Regional MetaApi
    # ========================================================================

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

            if self._backend == "metaapi":

                if not METAAPI_TOKEN:

                    self._set_error(
                        "METAAPI_TOKEN_MISSING",
                        "METAAPI_TOKEN is not configured.",
                    )

                    self._initialized = False

                    return False

                if not METAAPI_ACCOUNT_ID:

                    self._set_error(
                        "METAAPI_ACCOUNT_ID_MISSING",
                        (
                            "METAAPI_ACCOUNT_ID is not "
                            "configured."
                        ),
                    )

                    self._initialized = False

                    return False

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

    # ========================================================================
    # Login
    # ========================================================================

    def login(
        self,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
    ) -> bool:

        with self._lock:

            if self._backend == "metaapi":

                if not self._initialized:

                    if not self.initialize():
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

                    if (
                        connection_status
                        != "CONNECTED"
                    ):

                        self._set_error(
                            "METAAPI_ACCOUNT_NOT_CONNECTED",
                            (
                                "MetaApi account is "
                                "not connected to the "
                                "broker."
                            ),
                            details={
                                "state": (
                                    metadata.get(
                                        "state"
                                    )
                                ),
                                "connectionStatus": (
                                    connection_status
                                ),
                                "region": (
                                    metadata.get(
                                        "region"
                                    )
                                ),
                            },
                        )

                        return False

                    account = (
                        self._metaapi_get(
                            (
                                "/users/current/accounts/"
                                f"{quote(METAAPI_ACCOUNT_ID, safe='')}"
                                "/account-information"
                            )
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

                    self._clear_error()

                    return True

                except MetaApiError:

                    return False

                except Exception:

                    logger.exception(
                        "MetaApi login/readiness check failed."
                    )

                    self._set_error(
                        "METAAPI_LOGIN_FAILED",
                        (
                            "MetaApi account readiness "
                            "check failed."
                        ),
                    )

                    return False

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

                if not self.initialize():
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

                    result = (
                        self._mt5.login(
                            login,
                            password,
                            server,
                        )
                    )

                elif (
                    login is not None
                    and password is not None
                ):

                    result = (
                        self._mt5.login(
                            login,
                            password,
                        )
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

    # ========================================================================
    # Shutdown
    # ========================================================================

    def shutdown(
        self,
    ) -> bool:

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

                self._client_base_url = (
                    _explicit_client_base_url()
                )

                return True

            if not self._use_legacy():

                self._initialized = False
                return True

            try:

                result = (
                    self._mt5.shutdown()
                )

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
    ) -> Optional[
        Dict[str, Any]
    ]:

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
                "state": metadata.get("state"),
                "connectionStatus": metadata.get(
                    "connectionStatus"
                ),
                "region": metadata.get("region"),
                "type": metadata.get("type"),
                "server": metadata.get("server"),
                "login": metadata.get("login"),
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

    def version(
        self,
    ) -> Optional[str]:

        if self._backend == "metaapi":
            return "MetaApi REST"

        if not self._use_legacy():
            return None

        try:

            version = (
                self._mt5.version()
            )

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
    ) -> Optional[
        Dict[str, Any]
    ]:

        if self._last_error:
            return dict(self._last_error)

        if self._backend == "metaapi":
            return None

        if not self._use_legacy():
            return None

        try:

            last = (
                self._mt5.last_error()
            )

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
    ) -> Optional[
        Dict[str, Any]
    ]:

        if self._backend == "metaapi":

            try:

                account = (
                    self._metaapi_get(
                        (
                            "/users/current/accounts/"
                            f"{quote(METAAPI_ACCOUNT_ID, safe='')}"
                            "/account-information"
                        )
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
    ) -> List[
        Dict[str, Any]
    ]:

        if self._backend == "metaapi":

            try:

                positions = (
                    self._metaapi_get(
                        (
                            "/users/current/accounts/"
                            f"{quote(METAAPI_ACCOUNT_ID, safe='')}"
                            "/positions"
                        )
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
    ) -> List[
        Dict[str, Any]
    ]:

        if self._backend == "metaapi":

            try:

                symbols = (
                    self._metaapi_get(
                        (
                            "/users/current/accounts/"
                            f"{quote(METAAPI_ACCOUNT_ID, safe='')}"
                            "/symbols"
                        )
                    )
                )

                if not symbols:
                    return []

                if isinstance(
                    symbols,
                    list,
                ):

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
    # Symbol information
    # ========================================================================

    def symbol_info(
        self,
        symbol: str,
    ) -> Optional[
        Dict[str, Any]
    ]:

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
                            "/users/current/accounts/"
                            f"{quote(METAAPI_ACCOUNT_ID, safe='')}"
                            f"/symbols/{encoded_symbol}"
                            "/specification"
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
    ) -> Optional[
        Dict[str, Any]
    ]:

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

                tick = (
                    self._metaapi_get(
                        (
                            "/users/current/accounts/"
                            f"{quote(METAAPI_ACCOUNT_ID, safe='')}"
                            f"/symbols/{encoded_symbol}"
                            "/current-tick"
                        )
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

    def copy_rates_from_pos(
        self,
        symbol: str,
        timeframe: str,
        start_pos: int = 0,
        count: int = 500,
    ) -> List[Dict[str, Any]]:
        """Return bounded OHLC bars from the local MT5 terminal.

        The founder market-data release intentionally supports the Windows
        terminal only. MetaApi is not used as a silent fallback because doing
        so would obscure the broker source and chart provenance.
        """
        normalized_symbol = symbol.strip() if isinstance(symbol, str) else ""
        normalized_timeframe = timeframe.strip().upper() if isinstance(timeframe, str) else ""
        allowed = {
            "M1": "TIMEFRAME_M1",
            "M5": "TIMEFRAME_M5",
            "M15": "TIMEFRAME_M15",
            "H1": "TIMEFRAME_H1",
            "H4": "TIMEFRAME_H4",
            "D1": "TIMEFRAME_D1",
            "W1": "TIMEFRAME_W1",
        }

        if not normalized_symbol:
            self._set_error("INVALID_SYMBOL", "Symbol must be a non-empty string.")
            return []
        if normalized_timeframe not in allowed:
            self._set_error("INVALID_TIMEFRAME", "Timeframe is not allowlisted.")
            return []
        if not isinstance(start_pos, int) or start_pos < 0:
            self._set_error("INVALID_START_POSITION", "Start position must be a non-negative integer.")
            return []
        if not isinstance(count, int) or count < 1 or count > 10000:
            self._set_error("INVALID_BAR_COUNT", "Bar count must be between 1 and 10000.")
            return []
        if self._backend == "metaapi":
            self._set_error(
                "MARKET_BARS_UNSUPPORTED",
                "OHLC bars require the authenticated local MT5 terminal.",
            )
            return []
        if not self._use_legacy():
            return []

        try:
            timeframe_value = getattr(self._mt5, allowed[normalized_timeframe], None)
            if timeframe_value is None:
                self._set_error("TIMEFRAME_UNAVAILABLE", "MT5 timeframe constant is unavailable.")
                return []
            if hasattr(self._mt5, "symbol_select") and not self._mt5.symbol_select(normalized_symbol, True):
                self._set_error("SYMBOL_UNAVAILABLE", "MT5 could not select the requested symbol.")
                return []
            rates = self._mt5.copy_rates_from_pos(
                normalized_symbol,
                timeframe_value,
                start_pos,
                count,
            )
            if rates is None:
                return []
            records: List[Dict[str, Any]] = []
            for rate in rates:
                record = _as_dict(rate)
                if record is None:
                    field_names = getattr(getattr(rate, "dtype", None), "names", None)
                    if field_names:
                        record = {
                            name: rate[name].item() if hasattr(rate[name], "item") else rate[name]
                            for name in field_names
                        }
                if record is not None:
                    records.append(record)
            return records
        except Exception:
            logger.debug("mt5.copy_rates_from_pos() raised.", exc_info=True)
            return []

    # ========================================================================
    # History
    # ========================================================================

    def history_deals_get(
        self,
        from_dt: datetime.datetime,
        to_dt: datetime.datetime,
        ticket: Optional[int] = None,
        symbol: Optional[str] = None,
    ) -> List[
        Dict[str, Any]
    ]:

        if self._backend == "metaapi":

            try:

                account_id = quote(
                    METAAPI_ACCOUNT_ID,
                    safe="",
                )

                if ticket is not None:

                    path = (
                        "/users/current/accounts/"
                        f"{account_id}"
                        "/history-deals/ticket/"
                        f"{quote(str(ticket), safe='')}"
                    )

                    deals = (
                        self._metaapi_get(path)
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
                        "/users/current/accounts/"
                        f"{account_id}"
                        "/history-deals/time/"
                        f"{start}/{end}"
                    )

                    deals = (
                        self._metaapi_get(
                            path,
                            params={
                                "limit": 1000,
                                "offset": 0,
                            },
                        )
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

                    wanted = (
                        symbol.strip().upper()
                    )

                    result = [
                        deal
                        for deal in result
                        if str(
                            deal.get(
                                "symbol",
                                "",
                            )
                        ).upper()
                        == wanted
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

    def history_orders_get(
        self,
        from_dt: datetime.datetime,
        to_dt: datetime.datetime,
        ticket: Optional[int] = None,
        symbol: Optional[str] = None,
    ) -> List[
        Dict[str, Any]
    ]:

        if self._backend == "metaapi":

            try:

                account_id = quote(
                    METAAPI_ACCOUNT_ID,
                    safe="",
                )

                if ticket is not None:

                    path = (
                        "/users/current/accounts/"
                        f"{account_id}"
                        "/history-orders/ticket/"
                        f"{quote(str(ticket), safe='')}"
                    )

                    orders = (
                        self._metaapi_get(path)
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
                        "/users/current/accounts/"
                        f"{account_id}"
                        "/history-orders/time/"
                        f"{start}/{end}"
                    )

                    orders = (
                        self._metaapi_get(
                            path,
                            params={
                                "limit": 1000,
                                "offset": 0,
                            },
                        )
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

                    wanted = (
                        symbol.strip().upper()
                    )

                    result = [
                        order
                        for order in result
                        if str(
                            order.get(
                                "symbol",
                                "",
                            )
                        ).upper()
                        == wanted
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
