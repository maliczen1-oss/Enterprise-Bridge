"""
FastAPI authentication dependency.

Validates the ``Authorization: Bearer <token>`` header against the configured
``AUTH_TOKEN``.  Inject this dependency into any router that requires
authentication::

    router = APIRouter(dependencies=[Depends(require_auth)])

The ``/health`` endpoint is explicitly excluded from authentication in the
middleware layer; this dependency is never called for that route.
"""

from __future__ import annotations

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from bridge.core.exceptions import AuthenticationException

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """
    FastAPI dependency that enforces Bearer token authentication.

    Raises ``AuthenticationException`` (→ HTTP 401) when:
    - the ``Authorization`` header is absent or malformed, or
    - the provided token does not match the configured ``AUTH_TOKEN``.
    """
    from bridge.config import settings  # deferred to avoid circular import

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationException(
            "Missing or malformed Authorization header. "
            "Expected: Authorization: Bearer <token>"
        )

    if credentials.credentials != settings.auth_token:
        raise AuthenticationException("Invalid bearer token.")
