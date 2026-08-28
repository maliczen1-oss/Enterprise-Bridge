"""Run the WealthBuilder Enterprise Bridge with ``python -m bridge``."""

from __future__ import annotations

import uvicorn

from bridge.config import settings
from core.logging import configure_logging


def main() -> None:
    configure_logging(settings.LOG_LEVEL)
    uvicorn.run(
        "bridge.app:app",
        host=settings.HOST,
        port=settings.PORT,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
