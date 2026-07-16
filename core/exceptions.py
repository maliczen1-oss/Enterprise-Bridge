"""
Enterprise exception hierarchy for the WealthBuilder Bridge.

All exceptions inherit from BridgeBaseException to ensure consistent
error handling and response formatting across the entire application.
"""

from __future__ import annotations

from http import HTTPStatus


class BridgeBaseException(Exception):
    """
    Root exception for all WealthBuilder Bridge errors.

    Subclasses must supply a human-readable ``message``, an upper-snake-case
    ``code`` used in JSON error payloads, and the appropriate HTTP status code.
    Internal detail is kept server-side; only ``message`` is ever surfaced to
    callers.
    """

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


class AuthenticationException(BridgeBaseException):
    """Raised when a request lacks valid credentials."""

    status_code: int = HTTPStatus.UNAUTHORIZED
    code: str = "AUTHENTICATION_FAILED"

    def __init__(self, message: str = "Authentication required.") -> None:
        super().__init__(message)


class ValidationException(BridgeBaseException):
    """Raised when request input fails validation."""

    status_code: int = HTTPStatus.UNPROCESSABLE_ENTITY
    code: str = "VALIDATION_ERROR"

    def __init__(self, message: str = "Request validation failed.") -> None:
        super().__init__(message)


class InternalException(BridgeBaseException):
    """Raised for unexpected server-side failures."""

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str = "An internal error occurred.") -> None:
        super().__init__(message)


class ConfigurationException(BridgeBaseException):
    """Raised when required configuration is missing or invalid."""

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    code: str = "CONFIGURATION_ERROR"

    def __init__(self, message: str = "Server configuration error.") -> None:
        super().__init__(message)
