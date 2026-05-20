from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Normalized result for SDK tool calls."""

    value: object
    metadata: Mapping[str, Any]
