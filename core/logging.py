"""
Enterprise structured logging for the WealthBuilder Bridge.

Configures the root logger once at startup.  All modules obtain their logger
via ``get_logger(__name__)`` — never via ``print()``.

Log records include:
  - timestamp (ISO-8601 UTC)
  - level
  - logger name
  - message
  - request_id   (when available via contextvars)
  - arbitrary extra fields passed by the caller
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from bridge.core.request_context import get_request_id


class _StructuredFormatter(logging.Formatter):
    """
    Emit each log record as a single-line JSON object.

    Callers may attach arbitrary metadata by passing ``extra`` to the logging
    call::

        logger.info("order placed", extra={"order_id": 42})
    """

    _RESERVED: frozenset[str] = frozenset(
        {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "taskName",
            "message",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        record_dict: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }

        # Attach any extra fields the caller provided.
        for key, value in record.__dict__.items():
            if key not in self._RESERVED and not key.startswith("_"):
                record_dict[key] = value

        if record.exc_info:
            record_dict["exception"] = self.formatException(record.exc_info)

        return json.dumps(record_dict, default=str)


def configure_logging(level: str = "INFO") -> None:
    """
    Initialise structured logging for the entire application.

    Must be called exactly once, during application startup, before any other
    module emits a log record.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_StructuredFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric_level)

    # Quiet noisy third-party loggers.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").propagate = False


def get_logger(name: str) -> logging.Logger:
    """Return a named logger.  Call once per module: ``logger = get_logger(__name__)``."""
    return logging.getLogger(name)
