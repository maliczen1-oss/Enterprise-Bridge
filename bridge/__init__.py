"""Stable package namespace for the Enterprise Bridge application.

The historical repository stores application modules at its root.  This
compatibility package provides the documented ``bridge.*`` imports without
duplicating runtime modules or changing the existing public imports.
"""

from __future__ import annotations

__all__ = ["app"]

