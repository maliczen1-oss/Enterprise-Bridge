"""
pytest configuration for the WealthBuilder Bridge test suite.

Bootstraps the FastAPI application state (startup_time, connection_manager)
that is normally populated by the lifespan context manager.  The httpx
ASGITransport does not trigger lifespan events, so we replicate the relevant
startup logic here to keep tests self-contained.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import pytest
import pytest_asyncio

# Env vars must be in place before bridge.config is imported.
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("API_VERSION", "v1")
os.environ.setdefault("AUTH_TOKEN", "test-secret-token-for-pytest")
os.environ.setdefault("LOG_LEVEL", "WARNING")

from bridge.app import app  # noqa: E402
from bridge.core.connection_manager import ConnectionManager  # noqa: E402


@pytest_asyncio.fixture(autouse=True, scope="session")
async def bootstrap_app_state():
    """
    Initialise ``app.state`` once for the entire test session.

    Mirrors the startup sequence in ``bridge.app.lifespan`` without requiring
    a running ASGI server or a lifespan-aware transport.
    """
    cm = ConnectionManager()
    await cm.start()

    app.state.connection_manager = cm
    app.state.startup_time = datetime.now(tz=timezone.utc)
    app.state.startup_monotonic = time.monotonic()

    yield

    await cm.stop()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "asyncio: mark test as async")
