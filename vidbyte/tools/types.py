from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Stable public metadata for a Vidbyte SDK tool."""

    name: str
    description: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("ToolSpec name must be a non-empty string.")

