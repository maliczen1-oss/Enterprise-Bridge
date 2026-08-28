"""
Thread-/coroutine-safe request context propagation.

Uses a ``contextvars.ContextVar`` so that the current request ID is accessible
from any coroutine in the request call stack without passing it explicitly as a
parameter — including from the structured log formatter.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def set_request_id(request_id: str) -> None:
    """Store the current request's ID in the context."""
    _request_id_var.set(request_id)


def get_request_id() -> Optional[str]:
    """Retrieve the current request ID, or ``None`` if none is set."""
    return _request_id_var.get()


def clear_request_id() -> None:
    """Clear the current request ID without affecting another context."""
    _request_id_var.set(None)
