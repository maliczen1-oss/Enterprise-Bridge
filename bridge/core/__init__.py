"""Alias root ``core`` modules into the stable ``bridge.core`` namespace."""

from __future__ import annotations

import importlib
import sys

_MODULES = (
    "exceptions", "request_context", "models", "responses", "mt5_client",
    "connection_manager", "auth", "logging",
)

for _name in _MODULES:
    _module = importlib.import_module(f"core.{_name}")
    sys.modules[f"{__name__}.{_name}"] = _module
    globals()[_name] = _module

__all__ = list(_MODULES)
