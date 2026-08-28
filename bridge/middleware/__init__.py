"""Alias root middleware modules into ``bridge.middleware``."""

from __future__ import annotations

import importlib
import sys

_MODULES = ("auth", "logging", "request_id", "timing")

for _name in _MODULES:
    _module = importlib.import_module(f"middleware.{_name}")
    sys.modules[f"{__name__}.{_name}"] = _module
    globals()[_name] = _module

__all__ = list(_MODULES)

