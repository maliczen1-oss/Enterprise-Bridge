"""Run the WealthBuilder Enterprise Bridge with ``python -m bridge``."""

from __future__ import annotations

import uvicorn

from bridge.config import settings


def main() -> None:
    uvicorn.run(
        "bridge.app:app",
        host=settings.HOST,
        port=settings.PORT,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
