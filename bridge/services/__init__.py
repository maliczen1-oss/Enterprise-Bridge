"""Alias root service modules into the stable ``bridge.services`` namespace."""

from __future__ import annotations

import importlib
import sys

_MODULES = (
    "account_service", "history_service", "market_service", "position_service",
    "symbol_service", "trade_service",
)

for _name in _MODULES:
    _module = importlib.import_module(f"services.{_name}")
    sys.modules[f"{__name__}.{_name}"] = _module
    globals()[_name] = _module

__all__ = list(_MODULES)

