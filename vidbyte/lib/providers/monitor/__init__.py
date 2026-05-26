"""Context Protocol Header

Description:
    Re-exports monitor backend implementations.
Purpose:
    Provides a stable import surface for monitor provider backends without
    exposing internal implementation details.
Architecture:
    - BaseMonitorBackend: Abstract contract.
    - SubprocessMonitorBackend: Concrete asyncio subprocess backend.
Relations:
    Related to vidbyte.tools.builtins.monitor.
"""

from __future__ import annotations

from vidbyte.lib.providers.monitor.base import BaseMonitorBackend, MonitorInfo
from vidbyte.lib.providers.monitor.subprocess_backend import SubprocessMonitorBackend

__all__ = [
    "BaseMonitorBackend",
    "MonitorInfo",
    "SubprocessMonitorBackend",
]
