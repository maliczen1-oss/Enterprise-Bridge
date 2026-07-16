"""
Entry point for running the bridge directly::

    python -m bridge
"""

from __future__ import annotations

import uvicorn

from bridge.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "bridge.app:app",
        host=settings.host,
        port=settings.port,
        log_config=None,  # Disable Uvicorn's default logging; we own it.
        access_log=False,
    )
