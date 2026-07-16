"""
Application configuration.

All settings are read exclusively from environment variables (or a ``.env``
file in the working directory).  Required variables are validated at import
time so that misconfiguration surfaces as a startup failure — never as a
runtime surprise.

Usage
-----
::

    from bridge.config import settings

    print(settings.host)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from bridge.core.exceptions import ConfigurationException

# Load .env from the bridge/ directory (or CWD, whichever the caller prefers).
_env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=_env_path, override=False)


def _require(key: str) -> str:
    """Return the environment variable ``key`` or raise ``ConfigurationException``."""
    value = os.environ.get(key, "").strip()
    if not value:
        raise ConfigurationException(
            f"Required environment variable '{key}' is missing or empty. "
            "Check your .env file against .env.example."
        )
    return value


def _optional(key: str, default: str) -> str:
    return os.environ.get(key, default).strip() or default


class _Settings:
    """
    Immutable application settings resolved once at module load time.

    Attributes
    ----------
    host : str
        Bind address for the Uvicorn server.
    port : int
        Bind port for the Uvicorn server.
    environment : str
        Deployment environment label (``development``, ``staging``, ``production``).
    api_version : str
        Semantic version string for the API (e.g. ``"v1"``).
    log_level : str
        Python logging level name (``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``).
    auth_token : str
        Secret bearer token used to authenticate all protected endpoints.
        Never logged.
    request_timeout : float
        Maximum seconds to wait for upstream I/O (Phase 2.2+).
    app_title : str
        Human-readable application name surfaced in logs and the health endpoint.
    app_version : str
        Application release version string.
    """

    app_title: str = "WealthBuilder Bridge"
    app_version: str = "2.1.0"

    def __init__(self) -> None:
        self.host: str = _optional("HOST", "0.0.0.0")
        self.port: int = int(_optional("PORT", "8000"))
        self.environment: str = _require("ENVIRONMENT")
        self.api_version: str = _require("API_VERSION")
        self.log_level: str = _optional("LOG_LEVEL", "INFO").upper()
        self.auth_token: str = _require("AUTH_TOKEN")
        self.request_timeout: float = float(_optional("REQUEST_TIMEOUT", "30"))

        self._validate()

    def _validate(self) -> None:
        valid_environments = {"development", "staging", "production"}
        if self.environment not in valid_environments:
            raise ConfigurationException(
                f"ENVIRONMENT must be one of {sorted(valid_environments)!r}; "
                f"got {self.environment!r}."
            )

        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.log_level not in valid_levels:
            raise ConfigurationException(
                f"LOG_LEVEL must be one of {sorted(valid_levels)!r}; "
                f"got {self.log_level!r}."
            )

        if not (1 <= self.port <= 65535):
            raise ConfigurationException(
                f"PORT must be between 1 and 65535; got {self.port}."
            )

        if self.request_timeout <= 0:
            raise ConfigurationException(
                f"REQUEST_TIMEOUT must be a positive number; got {self.request_timeout}."
            )

    def __repr__(self) -> str:
        # Deliberately excludes auth_token.
        return (
            f"Settings("
            f"host={self.host!r}, "
            f"port={self.port}, "
            f"environment={self.environment!r}, "
            f"api_version={self.api_version!r}, "
            f"log_level={self.log_level!r}, "
            f"request_timeout={self.request_timeout}"
            f")"
        )


# Module-level singleton — imported by all other modules.
settings = _Settings()
