"""Context Protocol Header

Description:
    Defines the abstract base class and data transfer object for monitor backends.
Purpose:
    Provides a typed contract that all monitor provider backends must implement,
    along with the shared MonitorInfo dataclass for tracking subprocess state.
Architecture:
    - MonitorInfo: Dataclass holding monitor state, label, command, and output lines.
    - BaseMonitorBackend: ABC requiring start, stop, list_monitors, and read_output.
Relations:
    Related to vidbyte.lib.providers.monitor and vidbyte.tools.builtins.monitor.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(slots=True)
class MonitorInfo:
    """Runtime state for a single monitored subprocess."""

    id: str
    label: str
    command: str
    status: str
    lines: list[str] = field(default_factory=list)


class BaseMonitorBackend(ABC):
    """Abstract contract for subprocess monitor backends."""

    @abstractmethod
    async def start(self, command: str, label: str, workdir: str) -> str:
        """Start a new monitored subprocess and return its monitor ID."""
        ...

    @abstractmethod
    async def stop(self, monitor_id: str) -> str:
        """Stop a running monitor by ID and return its final status."""
        ...

    @abstractmethod
    async def list_monitors(self) -> list[MonitorInfo]:
        """Return a snapshot of all known monitors."""
        ...

    @abstractmethod
    async def read_output(self, monitor_id: str, since_line: int) -> dict:
        """Return output lines since a given index, total line count, and status."""
        ...


__all__ = [
    "BaseMonitorBackend",
    "MonitorInfo",
]
