from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Normalized result for SDK tool calls."""

    value: object
    metadata: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class FileStat:
    """Portable file metadata returned by filesystem stat operations."""

    path: str
    exists: bool
    is_file: bool
    is_dir: bool
    size: int | None
    modified_time: float | None


__all__ = [
    "FileStat",
    "ToolResult",
]
